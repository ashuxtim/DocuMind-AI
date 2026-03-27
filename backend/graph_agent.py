import os
import re
import json
import asyncio
import logging
from functools import lru_cache
from itertools import combinations
from typing import List, Dict, Optional, Tuple
from nameparser import HumanName
from llm_provider import get_llm_provider
from langsmith import traceable

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

ALLOWED_NODE_TYPES = {
    "Person", "Organization", "Location", "Technology", "Product",
    "Event", "Concept", "Document", "Law", "Date", "Amount"
}

# Only identity-bearing types get alias tracking.
# Concept / Document / Law / Date / Amount are contextual — storing aliases
# on them causes cross-document contamination and unbounded list growth.
ALIAS_ENABLED_TYPES = {"Person", "Organization"}

# Token-based query expansion for defined legal/financial terms.
# Keys are single lowercase tokens. At query time, any token in the question
# that matches a key appends the expansion terms to the keyword search list.
# Add entries here as new documents expose new blind spots.
LEGAL_TERM_EXPANSIONS: Dict[str, List[str]] = {
    "bridge":     ["IP Bridge Agreement", "IP Bridge"],
    "interim":    ["IP Bridge Agreement", "interim arrangement"],
    "temporary":  ["IP Bridge Agreement"],
    "closing":    ["Closing Date", "Closing Conditions"],
    "itar":       ["DDTC", "Directorate of Defense Trade Controls"],
    "regulatory": ["DDTC", "ITAR"],
}

# ALLOWED_EDGE_TYPES removed — LLM generates freely with formatting rules
# Edge normalisation pass handles consistency after extraction

EXTRACTION_PROMPT = """
You are a graph extraction engine. Your only job is to extract entities and
relationships from the text and return them as a JSON graph.

RULES:
1. Extract only entities that are explicitly mentioned in the text.
   Do not infer or add entities not present in the text.
2. Only extract NAMED, SPECIFIC entities — proper nouns, named people, named
   organizations, specific products, specific technologies, specific locations.
   NEVER extract generic nouns like "entities", "liabilities", "partners",
   "commitments", "team members", "shareholders", "management", "board",
   or any other common noun that is not a specific named thing.
3. Use only these node types: Person, Organization, Location, Technology,
   Product, Event, Concept, Document, Law, Date, Amount
4. For Person entities: ALWAYS use the full formal name.
   Never use surnames alone ("Chen"), initials alone ("S. Chen"),
   or citation format ("Chen, S."). Always write "Dr. Sarah Chen" not "Chen".
5. Relationship types MUST follow ALL of these rules:
   - SCREAMING_SNAKE_CASE only (e.g. WORKS_AT, FOUNDED_BY, DISPUTES_WITH)
   - 1 to 4 words maximum
   - Active verb form: ACQUIRED_BY not ACQUISITION_OF
   - Be specific: DISPUTES_WITH is better than RELATED_TO
   - Use RELATED_TO only as absolute last resort when nothing specific fits
   - NEVER invent vague types like HAS_COMMERCIAL_ENGAGEMENT_WITH
6. Every edge source_id and target_id must match an id in the nodes list.
7. Node id must be snake_case of the name. Node name must be Title Case.
8. Return ONLY valid JSON. No explanation. No markdown. No extra text.

OUTPUT SCHEMA:
{{"nodes": [{{"id": "...", "type": "...", "name": "...", "properties": {{}}}}],
  "edges": [{{"source_id": "...", "target_id": "...", "type": "...", "properties": {{}}}}]}}

EXAMPLE INPUT:
"Elon Musk founded Tesla in 2003. The company is headquartered in Austin."

EXAMPLE OUTPUT:
{{
  "nodes": [
    {{"id": "elon_musk", "type": "Person", "name": "Elon Musk", "properties": {{}}}},
    {{"id": "tesla", "type": "Organization", "name": "Tesla", "properties": {{}}}},
    {{"id": "austin", "type": "Location", "name": "Austin", "properties": {{}}}},
    {{"id": "2003", "type": "Date", "name": "2003", "properties": {{}}}}
  ],
  "edges": [
    {{"source_id": "elon_musk", "target_id": "tesla", "type": "FOUNDED_BY", "properties": {{}}}},
    {{"source_id": "tesla", "target_id": "austin", "type": "LOCATED_IN", "properties": {{}}}},
    {{"source_id": "tesla", "target_id": "2003", "type": "DATED", "properties": {{}}}}
  ]
}}

TEXT:
{chunk_text}
""".strip()

QUERY_PROMPT = """
Extract search keywords from this question for a knowledge graph lookup.
Include: people, organizations, dates, amounts, AND defined terms,
acronyms, or document-specific named concepts (e.g. named agreements,
regulatory frameworks, compliance standards, named indices).
Return ONLY a JSON array of 3-8 keywords.
Examples:
  ["Elon Musk", "Tesla", "2003"]
  ["IP Bridge Agreement", "DCA-7", "Closing Date"]
  ["IGDTA", "Intragroup Data Transfer Agreement", "Section 5.1"]
JSON array:
{question}
""".strip()

COREF_PROMPT = """
The following name groups were extracted from a single document and may refer to the same person or organization.
Each inner list is a group of names that rapidfuzz has already identified as potentially the same entity.
For each group, identify the canonical (most complete, most formal) name.

Return ONLY a JSON object mapping each non-canonical name to its canonical form.
Do not include canonical names as keys — only include names that need to be remapped.

Example:
Input: [["Chen", "Chen, S.", "Dr. Sarah Chen"], ["Smith", "J. Smith"]]
Output: {{"Chen": "Dr. Sarah Chen", "Chen, S.": "Dr. Sarah Chen", "Smith": "J. Smith"}}

Name groups to resolve:
{name_list}

JSON object:
""".strip()

EDGE_NORMALISE_PROMPT = """
The following relationship types were extracted from a document.
Some may be duplicates or near-synonyms that should be consolidated.
For each group of similar types, identify the best canonical form.

Return ONLY a JSON object mapping non-canonical types to their canonical form.
Do not include canonical types as keys.

Example:
Input: ["ACQUIRES", "ACQUIRED_BY", "HAS_ACQUIRED", "ACQUISITION_OF"]
Output: {{"ACQUIRES": "ACQUIRED_BY", "HAS_ACQUIRED": "ACQUIRED_BY", "ACQUISITION_OF": "ACQUIRED_BY"}}

Relationship types:
{edge_types}

JSON object:
""".strip()


# ── Normalisation ─────────────────────────────────────────────────────────────

def _normalise_node(node: dict) -> dict:
    name = " ".join(node["name"].strip().split()).title()
    node_id = re.sub(r"[^a-z0-9_]", "", name.lower().replace(" ", "_").replace("-", "_"))
    node_type = node["type"] if node["type"] in ALLOWED_NODE_TYPES else "Concept"
    if node_type != node["type"]:
        logger.warning("Remapped unknown node type '%s' to Concept", node["type"])
    return {**node, "name": name, "id": node_id, "type": node_type}


def _normalise_edge(edge: dict) -> dict:
    """Normalise edge type to SCREAMING_SNAKE_CASE. No allowed-list check."""
    raw = edge["type"].strip().upper()
    normalised = re.sub(r"[^A-Z0-9]+", "_", raw).strip("_")
    return {**edge, "type": normalised}


# ── Validation ────────────────────────────────────────────────────────────────

def _validate_graph(raw: dict) -> dict | None:
    if not isinstance(raw.get("nodes"), list) or not isinstance(raw.get("edges"), list):
        return None

    nodes = []
    for n in raw["nodes"]:
        if not isinstance(n, dict):
            return None
        if not all(k in n for k in ("id", "type", "name")):
            return None
        nodes.append(_normalise_node(n))

    valid_ids = {n["id"] for n in nodes}

    edges = []
    for e in raw["edges"]:
        if not isinstance(e, dict):
            continue
        e = _normalise_edge(e)
        if e.get("source_id") in valid_ids and e.get("target_id") in valid_ids:
            edges.append(e)
        else:
            logger.warning("Removed dangling edge: %s -> %s",
                           e.get("source_id"), e.get("target_id"))

    return {"nodes": nodes, "edges": edges}


# ── Merge Guards ──────────────────────────────────────────────────────────────

def _strip_suffixes(name: str) -> str:
    """
    Strip post-nominal credentials before nameparser comparison.
    Handles: "Dr. Patricia Nwankwo, PhD, SHRM-SCP" → "Dr. Patricia Nwankwo"
    Removes trailing comma-separated credential tokens only — not mid-name commas.
    """
    return re.sub(
        r',\s*[A-Z][A-Za-z\-\.]+(?:\s*,\s*[A-Z][A-Za-z\-\.]+)*$',
        '',
        name
    ).strip()


def should_block_merge(a: str, b: str) -> bool:
    """
    Returns True if two Person names must NOT be merged.
    Uses nameparser.HumanName for reliable first/last extraction.

    Truth table:
      - Both have first + last, first same, last differs  → BLOCK  (Gerald Ashford vs Gerald Fontaine)
      - Both have first + last, first differs, last differs → BLOCK  (different people entirely)
      - Both have first + last, first differs, last same   → ALLOW  (siblings / different people same family)
      - One is surname-only                                → ALLOW  (topology pass handles this)
      - Neither has a parsed first name                   → ALLOW  (fall through to rapidfuzz)
    """
    na = HumanName(_strip_suffixes(a))
    nb = HumanName(_strip_suffixes(b))

    # Surname-only detection: if either name is a single token
    # and that token appears as a word in the other name,
    # this is a surname-only form — allow through for topology pass.
    a_tokens = _strip_suffixes(a).split()
    b_tokens = _strip_suffixes(b).split()
    if len(a_tokens) == 1 and a_tokens[0].lower() in _strip_suffixes(b).lower().split():
        return False  # surname-only form of longer name — allow
    if len(b_tokens) == 1 and b_tokens[0].lower() in _strip_suffixes(a).lower().split():
        return False  # surname-only form of longer name — allow

    both_have_first = bool(na.first and nb.first)
    if not both_have_first:
        return False  # Can't compare — let rapidfuzz decide

    first_differ = na.first.lower() != nb.first.lower()
    last_differ  = na.last.lower()  != nb.last.lower()

    # Same first, different last → definitely different people
    if not first_differ and last_differ:
        return True

    # Different first AND different last → different people
    if first_differ and last_differ:
        return True

    return False


# ── Entity Registry ───────────────────────────────────────────────────────────

def _build_entity_registry(
    all_graphs: List[dict],
    target_types: set = None
) -> Tuple[Dict[str, str], List[List[str]]]:
    """
    Cluster similar entity names using rapidfuzz.
    Returns:
        auto_registry: high-confidence mappings (>= 85 similarity) — no LLM needed
        ambiguous_clusters: uncertain clusters (60-84 similarity) — needs LLM
    """
    from rapidfuzz import fuzz

    if target_types is None:
        target_types = {"Person", "Organization"}

    # Collect all unique names for target types across all chunks
    name_set: Dict[str, str] = {}  # name → type
    for graph in all_graphs:
        for node in graph.get("nodes", []):
            if node["type"] in target_types:
                name_set[node["name"]] = node["type"]

    names = list(name_set.keys())
    if len(names) < 2:
        return {}, []

    # Cluster by token_sort_ratio similarity
    assigned = set()
    clusters: List[List[str]] = []

    for i, name_a in enumerate(names):
        if name_a in assigned:
            continue
        cluster = [name_a]
        assigned.add(name_a)
        for name_b in names[i + 1:]:
            if name_b in assigned:
                continue
            if fuzz.token_sort_ratio(name_a, name_b) >= 60:
                # Nameparser guard — runs before any Person is added to a cluster.
                # Blocks same-first/different-last merges (Gerald Ashford vs Gerald Fontaine).
                # Only applies to Person nodes — Orgs use rapidfuzz + LLM path.
                if name_set.get(name_a) == "Person" and name_set.get(name_b) == "Person":
                    if should_block_merge(name_a, name_b):
                        logger.info("🚫 Blocked merge: '%s' ≠ '%s' (nameparser guard)",
                                    name_a, name_b)
                        continue
                cluster.append(name_b)
                assigned.add(name_b)

        # Post-cluster safety net — validates ALL pairs in the completed cluster.
        # Catches cases where two blocked names entered the same cluster via
        # a third bridging name. If any blocked pair is found, the entire cluster
        # is discarded back to singletons — no partial merges.
        if len(cluster) > 1:
            has_conflict = any(
                name_set.get(x) == "Person"
                and name_set.get(y) == "Person"
                and should_block_merge(x, y)
                for x, y in combinations(cluster, 2)
            )
            if has_conflict:
                logger.info(
                    "🚫 Post-cluster conflict — splitting cluster back to singletons: %s",
                    cluster
                )
                # Remove non-pivot members from assigned so they can
                # still form valid clusters with other names.
                # The pivot (name_a) stays assigned — it was processed.
                for name in cluster[1:]:
                    assigned.discard(name)
                continue
            clusters.append(cluster)

    auto_registry: Dict[str, str] = {}
    ambiguous_clusters: List[List[str]] = []

    for cluster in clusters:
        # Max pairwise similarity in this cluster
        max_sim = max(
            fuzz.token_sort_ratio(cluster[i], cluster[j])
            for i in range(len(cluster))
            for j in range(i + 1, len(cluster))
        )
        # Canonical = longest name (most qualified form)
        canonical = max(cluster, key=len)

        if max_sim >= 85:
            for name in cluster:
                if name != canonical:
                    auto_registry[name] = canonical
            logger.info("Auto-merged → '%s': %s", canonical, cluster)
        else:
            ambiguous_clusters.append(cluster)

    return auto_registry, ambiguous_clusters


def _apply_registry_to_graphs(
    all_graphs: List[dict],
    registry: Dict[str, str]
) -> List[dict]:
    """
    Rewrite node names and ids across all graphs using the registry.
    Updates all edge source_id and target_id to match new ids.
    Deduplicates nodes that resolve to the same canonical name.

    For ALIAS_ENABLED_TYPES (Person, Organization): stores the list of absorbed
    names as node["properties"]["aliases"] so knowledge_graph.py can persist them
    to Neo4j with safe list-merge Cypher (never via SET n += which overwrites).
    """
    if not registry:
        return all_graphs

    # Build reverse map: canonical_name → [absorbed names] for alias-enabled types
    # Used to populate aliases property on canonical nodes before Neo4j write.
    canonical_to_aliases: Dict[str, List[str]] = {}
    for absorbed, canonical in registry.items():
        canonical_to_aliases.setdefault(canonical, []).append(absorbed)

    def to_id(name: str) -> str:
        return re.sub(r"[^a-z0-9_]", "",
                      name.lower().replace(" ", "_").replace("-", "_"))

    updated_graphs = []
    for graph in all_graphs:
        id_remap: Dict[str, str] = {}  # old_id → new_id

        new_nodes = []
        for node in graph.get("nodes", []):
            old_name = node["name"]
            new_name = registry.get(old_name, old_name)
            new_id = to_id(new_name)
            old_id = node["id"]
            if old_id != new_id:
                id_remap[old_id] = new_id

            new_props = dict(node.get("properties", {}))

            # Store absorbed aliases on identity-bearing nodes only.
            # Passed as a separate property so knowledge_graph.py can use
            # safe list-merge Cypher rather than SET n += which overwrites.
            if node["type"] in ALIAS_ENABLED_TYPES and new_name in canonical_to_aliases:
                new_props["aliases"] = canonical_to_aliases[new_name]

            new_nodes.append({**node, "name": new_name, "id": new_id,
                               "properties": new_props})

        # Deduplicate nodes merged to same id — keep first occurrence
        seen: Dict[str, bool] = {}
        deduped_nodes = []
        for node in new_nodes:
            if node["id"] not in seen:
                seen[node["id"]] = True
                deduped_nodes.append(node)

        # Remap edges to new ids, drop dangling
        valid_ids = {n["id"] for n in deduped_nodes}
        new_edges = []
        for edge in graph.get("edges", []):
            src = id_remap.get(edge["source_id"], edge["source_id"])
            tgt = id_remap.get(edge["target_id"], edge["target_id"])
            if src in valid_ids and tgt in valid_ids and src != tgt:
                new_edges.append({**edge, "source_id": src, "target_id": tgt})

        updated_graphs.append({"nodes": deduped_nodes, "edges": new_edges})

    return updated_graphs


# ── GraphBuilder ──────────────────────────────────────────────────────────────

class GraphBuilder:
    def __init__(self):
        self.llm = get_llm_provider(role="extraction")
        self.model_name = self.llm.get_model_name()
        print(f"🤖 GraphBuilder initialized with: {self.model_name}")

        if not os.getenv("LANGCHAIN_API_KEY"):
            print("⚠️  LangSmith tracing DISABLED — LANGCHAIN_API_KEY not set")
        else:
            print("✅ LangSmith tracing enabled")

        # Initialise merge registry state — populated by apply_entity_registry()
        self.last_auto_registry: Dict[str, str] = {}
        self.last_llm_registry: Dict[str, str] = {}

    def _parse_json_dict(self, response: str) -> dict:
        clean = re.sub(r'```(?:json)?', '', response).strip()
        match = re.search(r'\{.*\}', clean, re.DOTALL)
        if not match:
            return {}
        try:
            result = json.loads(match.group())
            return result if isinstance(result, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _parse_json_list(self, response: str) -> list:
        clean = re.sub(r'```(?:json)?', '', response).strip()
        match = re.search(r'\[.*\]', clean, re.DOTALL)
        if not match:
            return []
        try:
            result = json.loads(match.group())
            return result if isinstance(result, list) else []
        except json.JSONDecodeError:
            return []

    @traceable(name="graph_extraction")
    def extract_relationships(
        self,
        text_chunk: str,
        chunk_id: str = "",
        document_id: str = ""
    ) -> dict:
        """
        Full extraction pipeline for one chunk.
        Returns graph dict {nodes, edges} ready for ingest_graph().
        Never raises — returns empty graph on total failure.
        """
        prompt = EXTRACTION_PROMPT.format(chunk_text=text_chunk)

        for attempt in range(3):
            try:
                raw_text = self.llm.generate(prompt)
                raw = self._parse_json_dict(raw_text)
                graph = _validate_graph(raw)

                if graph is not None:
                    for node in graph["nodes"]:
                        node["properties"]["document_id"] = document_id
                        node["properties"]["chunk_id"] = chunk_id
                    for edge in graph["edges"]:
                        edge["properties"]["document_id"] = document_id
                        edge["properties"]["chunk_id"] = chunk_id
                    return graph

                logger.warning("Validation failed attempt %d chunk %s", attempt + 1, chunk_id)

            except json.JSONDecodeError as e:
                logger.warning("JSON parse failed attempt %d chunk %s: %s",
                               attempt + 1, chunk_id, e)
            except Exception as e:
                logger.warning("LLM call failed attempt %d chunk %s: %s",
                               attempt + 1, chunk_id, e)

        logger.error("Graph extraction failed after 3 attempts for chunk %s", chunk_id)
        return {"nodes": [], "edges": []}

    async def extract_relationships_batch(
        self,
        chunks: List[str],
        concurrency: int = 5
    ) -> List[dict]:
        sem = asyncio.Semaphore(concurrency)

        async def extract_one(chunk: str) -> dict:
            async with sem:
                return await asyncio.to_thread(self.extract_relationships, chunk)

        results = await asyncio.gather(*[extract_one(c) for c in chunks])
        return list(results)

    def _resolve_ambiguous_with_llm(
        self,
        ambiguous_clusters: List[List[str]]
    ) -> Dict[str, str]:
        """
        Send ambiguous name clusters to LLM for coreference resolution.
        Only called for clusters where rapidfuzz confidence is 60-84.
        Returns registry additions from LLM disambiguation.
        """
        if not ambiguous_clusters:
            return {}

        prompt = COREF_PROMPT.format(name_list=json.dumps(ambiguous_clusters, indent=2))


        try:
            response = self.llm.generate(prompt)
            result = self._parse_json_dict(response)
            if isinstance(result, dict):
                logger.info("LLM resolved %d ambiguous name mappings", len(result))
                return result
        except Exception as e:
            logger.warning("LLM coreference resolution failed: %s", e)

        return {}

    def _normalise_edge_types(self, all_graphs: List[dict]) -> List[dict]:
        """
        Collect all unique edge types across all graphs.
        Send full unique list to LLM for semantic normalisation.
        rapidfuzz removed — string similarity is blind to semantic synonyms
        like ACQUIRED_BY / PURCHASED_BY. LLM handles both spelling and semantics.
        """
        edge_types = list({
            edge["type"]
            for graph in all_graphs
            for edge in graph.get("edges", [])
        })

        if len(edge_types) < 2:
            return all_graphs

        prompt = EDGE_NORMALISE_PROMPT.format(
            edge_types=json.dumps(edge_types, indent=2)
        )
        edge_registry: Dict[str, str] = {}
        try:
            response = self.llm.generate(prompt)
            llm_registry = self._parse_json_dict(response)
            if isinstance(llm_registry, dict):
                edge_registry.update(llm_registry)
                logger.info("LLM normalised %d edge type mappings", len(llm_registry))
        except Exception as e:
            logger.warning("LLM edge normalisation failed: %s", e)

        if not edge_registry:
            return all_graphs

        updated = []
        for graph in all_graphs:
            new_edges = [
                {**e, "type": edge_registry.get(e["type"], e["type"])}
                for e in graph.get("edges", [])
            ]
            updated.append({**graph, "edges": new_edges})

        logger.info("Edge normalisation: %d types remapped", len(edge_registry))
        return updated

    def apply_entity_registry(self, all_graphs: List[dict]) -> List[dict]:
        """
        Full post-extraction deduplication pipeline.
        Called in ingest.py between Phase B (extraction) and Phase C (Neo4j write).

        Steps:
        1. Cluster entity names with rapidfuzz
        2. Auto-merge high-confidence clusters
        3. LLM resolves ambiguous clusters
        4. Apply registry — rewrite all node names and edge ids
        5. Normalise edge types
        """
        if not all_graphs:
            return all_graphs

        total_nodes_before = sum(len(g.get("nodes", [])) for g in all_graphs)
        print(f"   🔍 Entity registry: analysing {total_nodes_before} nodes across "
            f"{len(all_graphs)} chunks...")

        # Step 1+2: rapidfuzz clustering
        auto_registry, ambiguous_clusters = _build_entity_registry(all_graphs)

        # Step 3: LLM for ambiguous cases only
        llm_registry = self._resolve_ambiguous_with_llm(ambiguous_clusters)

        # Step 4: Merge and apply
        full_registry = {**auto_registry, **llm_registry}

        if full_registry:
            print(f"   ✅ Entity registry: {len(full_registry)} name(s) resolved "
                f"({len(auto_registry)} auto, {len(llm_registry)} via LLM)")
        else:
            print(f"   ✅ Entity registry: no duplicates detected")

        all_graphs = _apply_registry_to_graphs(all_graphs, full_registry)

        # Step 4b: Store merge registries so ingest.py can write
        # MERGED_INTO provenance edges AFTER nodes exist in Neo4j.
        self.last_auto_registry = auto_registry
        self.last_llm_registry = llm_registry

        # Step 5: Edge type normalisation
        all_graphs = self._normalise_edge_types(all_graphs)

        total_nodes_after = sum(len(g.get("nodes", [])) for g in all_graphs)
        if total_nodes_before != total_nodes_after:
            print(f"   📉 Node count: {total_nodes_before} → {total_nodes_after} "
                f"({total_nodes_before - total_nodes_after} duplicates removed)")

        return all_graphs

    @traceable(name="entity_extraction")
    @lru_cache(maxsize=512)
    def extract_query_entities(self, question: str) -> tuple:
        """
        LLM-based keyword extraction for graph search at query time.
        Returns tuple for lru_cache hashability.
        Call site: list(agent.extract_query_entities(question))

        After LLM extraction, runs token-based expansion via LEGAL_TERM_EXPANSIONS
        to catch defined legal/financial terms that LLM NER misses (e.g. "IP Bridge
        Agreement" from a query phrased as "interim arrangement").
        """
        try:
            response_text = self.llm.generate(
                QUERY_PROMPT.format(question=question)
            )
            result = self._parse_json_list(response_text)
            if result:
                keywords = list(result[:8])

                # Token-based expansion — check every word in the original question
                # against LEGAL_TERM_EXPANSIONS keys (lowercase single tokens).
                question_tokens = question.lower().split()
                expansions = []
                for token in question_tokens:
                    clean_token = re.sub(r"[^a-z]", "", token)
                    if clean_token in LEGAL_TERM_EXPANSIONS:
                        expansions.extend(LEGAL_TERM_EXPANSIONS[clean_token])

                if expansions:
                    # Deduplicate while preserving order — expansions appended after LLM keywords
                    seen = set(keywords)
                    for exp in expansions:
                        if exp not in seen:
                            keywords.append(exp)
                            seen.add(exp)
                    logger.info("Query expansion added: %s", expansions)

                # Strip honorifics so "Mr. Raymond Voss" → "Raymond Voss"
                # matches Neo4j fulltext which stores question-phrased names.
                HONORIFICS = {"mr.", "ms.", "mrs.", "dr.", "prof.", "mx."}
                def _strip_honorific(name: str) -> str:
                    parts = name.strip().split()
                    if parts and parts[0].lower().rstrip(".") + "." in HONORIFICS:
                        return " ".join(parts[1:])
                    return name

                return tuple(_strip_honorific(k) for k in keywords)
        except Exception:
            pass
        return tuple(w for w in question.split() if len(w) > 4)


# ── Singleton ─────────────────────────────────────────────────────────────────

_graph_builder_instance: Optional[GraphBuilder] = None


def get_graph_builder() -> GraphBuilder:
    global _graph_builder_instance
    if _graph_builder_instance is None:
        _graph_builder_instance = GraphBuilder()
    return _graph_builder_instance
