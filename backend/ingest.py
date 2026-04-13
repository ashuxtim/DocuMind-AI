import os
import logging
import re
import json
import hashlib
import asyncio
import redis
from typing import List, Dict
from vector_store import VectorStore
from parser import SmartPDFParser
from graph_agent import get_graph_builder
from knowledge_graph import KnowledgeBase

logger = logging.getLogger(__name__)

# "vllm" removed — vLLM provider is no longer part of the stack
CLOUD_PROVIDERS = {"openai", "gemini", "groq", "anthropic", "cohere", "nvidia"}


# ── Alias Pre-Pass (Stage 0) ──────────────────────────────────────────────────
# Runs BEFORE chunking on every ingest.
# Builds a flat lookup of alias → canonical so graph extraction never creates
# duplicate nodes for "Target" vs "Vantage Systems, Inc." vs "Acquired Entity".

DEFINITION_PATTERNS = [
    r'\((?:the\s+)?["\u201c\u201d\u2018\u2019]([A-Z][a-zA-Z\s\-]+)["\u201c\u201d\u2018\u2019]\)',
    r'hereinafter\s+(?:referred\s+to\s+as\s+)?["\u201c\u201d]([^"\u201d]+)["\u201c\u201d]',
    r'\(collectively[,\s]+(?:the\s+)?["\u201c\u201d]([^"\u201d]+)["\u201c\u201d]\)',
    r'["\u201c]([A-Z][a-zA-Z\s\-]+)["\u201d]\s*(?:means|shall mean|refers to)',
]

DEFINITION_HEADERS = re.compile(
    r'(article\s+i\b|section\s+1\b|definitions|defined terms|appendix\s+[a-z])',
    re.IGNORECASE
)

# Seed terms that must always be in the alias prompt regardless of document content.
# Add entries here as new documents expose new retrieval blind spots.
ALIAS_PROMPT_SEEDS = [
    "IP Bridge Agreement",
    "IP Bridge",
]

ALIAS_BUILD_PROMPT = """
You are reading a section of a legal or business document.
Extract every place where the document explicitly defines a shorthand,
alias, or defined term for an entity.

CRITICAL DEFINITION — canonical vs alias:
- "canonical" = the FULL FORMAL LEGAL NAME as it appears in official
  headers, signature blocks, or incorporation documents.
  It is almost always the LONGER name.
  Examples: "Vantage Systems, Inc.", "Meridian-Hartwell Consolidated Holdings, LP"
- "aliases" = the SHORTHAND or DEFINED TERM used for convenience.
  It is almost always SHORTER than the canonical.
  Examples: "Target", "Acquired Entity", "MHCH", "Acquirer", "the Company"

A parenthetical like (the "Target") means "Target" is an ALIAS —
NOT the canonical. The full name before the parenthetical IS the canonical.

Return ONLY a JSON array, no other text:
[
  {{ "canonical": "Vantage Systems, Inc.", "aliases": ["Target", "Acquired Entity", "Vantage"] }},
  {{ "canonical": "Meridian-Hartwell Consolidated Holdings, LP", "aliases": ["MHCH", "Acquirer"] }}
]

Rules:
- ONLY extract explicitly stated mappings — do NOT infer
- canonical must ALWAYS be the longer, more formal name
- aliases must ALWAYS be shorter shorthands or abbreviations
- Include: "hereinafter referred to as" patterns
- Include: parenthetical definitions like (the "Buyer")
- Include: abbreviation definitions like Federal Trade Commission ("FTC")
- Include: defined term tables (two-column format)
- Do NOT include people names or job titles
- Pay special attention to these terms if present: {seeds}

Document section:
{alias_window}
""".strip()


def _extract_alias_window(raw_text: str) -> str:
    """
    Three-layer extraction to find alias/definition sections in a document.

    Layer 1 — section header: finds "Definitions", "Article I", "Appendix A" etc.
    Layer 2 — regex patterns: finds parenthetical and hereinafter definitions anywhere.
    Layer 3 — positional fallback: first 3000 + last 1000 tokens (definitions often
               appear at document start and appendices at the end).

    Returns deduplicated paragraphs joined for LLM alias pass.
    """
    paragraphs = []

    # Layer 1: definition section header
    match = DEFINITION_HEADERS.search(raw_text)
    if match:
        start = match.start()
        paragraphs.append(raw_text[start:start + 8000])

    # Layer 2: regex pattern matches — collect surrounding paragraphs
    for pattern in DEFINITION_PATTERNS:
        for m in re.finditer(pattern, raw_text, re.IGNORECASE):
            para_start = max(0, raw_text.rfind('\n', 0, m.start()))
            para_end = raw_text.find('\n\n', m.end())
            para_end = para_end if para_end != -1 else m.end() + 500
            paragraphs.append(raw_text[para_start:para_end])

    # Layer 3: positional fallback
    tokens = raw_text.split()
    if len(tokens) > 4000:
        front = " ".join(tokens[:3000])
        back = " ".join(tokens[-1000:])
        paragraphs.append(front + "\n\n[...]\n\n" + back)
    else:
        paragraphs.append(raw_text)

    # Deduplicate by MD5 of first 200 chars — same paragraph can appear in
    # multiple layers without bloating the LLM prompt
    seen = set()
    unique = []
    for p in paragraphs:
        h = hashlib.md5(p[:200].encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            unique.append(p)

    return "\n\n---\n\n".join(unique)


def _build_alias_registry(alias_window: str, llm) -> Dict[str, str]:
    """
    One LLM call on the alias window.
    Returns flat normalized lookup: { "normalized_alias": "Canonical Name" }

    Normalization: lowercase, strip leading "the ", strip whitespace.
    This matches how apply_alias_resolution queries the registry.
    """
    prompt = ALIAS_BUILD_PROMPT.format(
        alias_window=alias_window,
        seeds=", ".join(ALIAS_PROMPT_SEEDS)
    )

    registry: Dict[str, str] = {}
    try:
        from llm_provider import get_llm_provider
        llm_instance = llm or get_llm_provider(role="extraction")
        response = llm_instance.generate(prompt)

        # Strip markdown fences before parsing
        clean = re.sub(r'```(?:json)?', '', response).strip()
        match = re.search(r'\[.*\]', clean, re.DOTALL)
        if not match:
            print("   ⚠️ Alias registry: LLM returned no JSON array")
            return registry

        entries = json.loads(match.group())
        if not isinstance(entries, list):
            return registry

        for entry in entries:
            canonical = entry.get("canonical", "").strip()
            aliases = [a.strip() for a in entry.get("aliases", []) if a.strip()]
            if not canonical or not aliases:
                continue

            # Length guard: if LLM inverted canonical and alias,
            # swap them. The canonical is almost always longer
            # than any of its aliases. If the stated canonical
            # is shorter than the longest alias, the LLM got it
            # backwards — promote the longest alias to canonical.
            longest_alias = max(aliases, key=len)
            if len(longest_alias) > len(canonical):
                logger.info(
                    "   🔄 Canonical direction corrected: '%s' → '%s'",
                    canonical, longest_alias
                )
                aliases = [a for a in aliases if a != longest_alias]
                aliases.append(canonical)
                canonical = longest_alias

            for alias in aliases:
                normalized = alias.lower().strip()
                if normalized.startswith("the "):
                    normalized = normalized[4:].strip()
                if normalized and normalized != canonical.lower():
                    registry[normalized] = canonical

        print(f"   📎 Alias registry built: {len(registry)} alias→canonical mappings")

    except json.JSONDecodeError as e:
        print(f"   ⚠️ Alias registry: JSON parse failed: {e}")
    except Exception as e:
        print(f"   ⚠️ Alias registry: LLM call failed: {e}")

    return registry


def _apply_alias_resolution(raw_graphs: List[dict], alias_registry: Dict[str, str]) -> List[dict]:
    """
    Deterministic alias resolution pass — runs AFTER graph extraction, BEFORE
    entity registry (dedup). Replaces alias forms with canonical names so the
    entity registry never sees "Target" and "Vantage Systems, Inc." as separate
    nodes to cluster.

    Uses RapidFuzz >95 threshold for OCR noise variants
    (e.g. "Meridian Hartwell" vs "Meridian-Hartwell").

    Only rewrites Organization and Person nodes — same ALIAS_ENABLED_TYPES
    invariant as graph_agent.py.
    """
    if not alias_registry:
        return raw_graphs

    from rapidfuzz import process as fuzz_process
    from graph_agent import ALIAS_ENABLED_TYPES

    substitutions = 0

    for graph in raw_graphs:
        # Build old_id → new_id map DURING the node rewrite loop,
        # capturing old_id BEFORE it is overwritten.
        # Used after the loop to remap stale edge source_id/target_id.
        id_remap: Dict[str, str] = {}

        for node in graph.get("nodes", []):
            if node.get("type") not in ALIAS_ENABLED_TYPES:
                continue

            name = node["name"]
            normalized = name.lower().strip()
            if normalized.startswith("the "):
                normalized = normalized[4:].strip()

            # Exact match first
            if normalized in alias_registry:
                canonical = alias_registry[normalized]
                old_id = node["id"]
                new_id = re.sub(
                    r"[^a-z0-9_]", "",
                    canonical.lower().replace(" ", "_").replace("-", "_")
                )
                print(f"   📎 Alias resolved: '{name}' → '{canonical}'")
                node["name"] = canonical
                node["id"] = new_id
                if old_id != new_id:
                    id_remap[old_id] = new_id
                substitutions += 1
                continue

            # Fuzzy match for OCR variants — high threshold to avoid false positives
            match = fuzz_process.extractOne(
                normalized,
                alias_registry.keys(),
                score_cutoff=95
            )
            if match:
                canonical = alias_registry[match[0]]
                old_id = node["id"]
                new_id = re.sub(
                    r"[^a-z0-9_]", "",
                    canonical.lower().replace(" ", "_").replace("-", "_")
                )
                print(f"   📎 Fuzzy alias resolved: '{name}' → '{canonical}' "
                      f"(score: {match[1]:.0f})")
                node["name"] = canonical
                node["id"] = new_id
                if old_id != new_id:
                    id_remap[old_id] = new_id
                substitutions += 1

        # Remap stale edge endpoints using old_id → new_id captured above.
        # Only runs when at least one id actually changed.
        if id_remap:
            for edge in graph.get("edges", []):
                if edge.get("source_id") in id_remap:
                    edge["source_id"] = id_remap[edge["source_id"]]
                if edge.get("target_id") in id_remap:
                    edge["target_id"] = id_remap[edge["target_id"]]

    if substitutions:
        print(f"   ✅ Alias resolution: {substitutions} node(s) resolved to canonical form")

    return raw_graphs


class DocuMindIngest:
    def __init__(self):
        self.vector_db = VectorStore()
        self.parser = SmartPDFParser()
        self.agent = get_graph_builder()
        self.kb = KnowledgeBase()

        self.provider = os.getenv("LLM_PROVIDER", "nvidia").lower()
        self.is_cloud = self.provider in CLOUD_PROVIDERS
        self.concurrency = 5 if self.is_cloud else 1

        # Redis client for the lifetime of this ingestor.
        # NOTE: no longer used for inference locking (Ollama lock removed).
        # Retained for job queue usage in main.py — remove here if job queue
        # manages its own Redis connection independently.
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        self.redis_client = redis.Redis.from_url(redis_url)

        # Global semaphore — controls concurrency across all documents
        self.semaphore = asyncio.Semaphore(self.concurrency)

        print(f"⚙️ Ingestion Mode: {self.provider.upper()} | Cloud: {self.is_cloud} | Concurrency: {self.concurrency}x")

    async def cleanup(self, filename: str):
        """Wipes all traces of a file from all stores."""
        print(f"🧹 CLEANUP PROTOCOL INITIATED for {filename}")
        try:
            self.vector_db.delete_file(filename)
            print("   - Vector entries deleted")
        except Exception as e:
            print(f"   - Vector delete warning: {e}")

        try:
            self.kb.delete_document(filename)
            print("   - Graph entries deleted")
        except Exception as e:
            print(f"   - Graph delete warning: {e}")

    async def _call_with_retry(self, fn, *args, max_retries: int = 3, base_delay: float = 2.0):
        """
        Retry a blocking call wrapped in asyncio.to_thread with exponential backoff.
        Handles rate limits and transient errors.
        """
        for attempt in range(max_retries):
            try:
                return await asyncio.to_thread(fn, *args)
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = "429" in err_str or "rate limit" in err_str or "quota" in err_str
                is_last = attempt == max_retries - 1

                if is_last:
                    raise

                delay = base_delay * (2 ** attempt)
                if is_rate_limit:
                    print(f"   ⏳ Rate limit — retrying in {delay:.0f}s ({attempt+2}/{max_retries})...")
                else:
                    print(f"   ⚠️ LLM error attempt {attempt+1} — retrying in {delay:.0f}s: {e}")

                await asyncio.sleep(delay)

    async def process_document(self, file_path: str, filename: str, cancellation_token):
        """Orchestrates ingestion: Dedup -> Stage0(Alias) -> Parse -> Vector (batch) -> Graph (concurrent)"""
        print(f"🚀 Processing: {filename}")

        try:
            # Dedup — always wipe prior data for clean re-ingest
            await self.cleanup(filename)

            # ── Stage 0: Alias pre-pass ───────────────────────────────────────
            # Runs on raw markdown BEFORE chunking so alias definitions that
            # straddle chunk boundaries are never missed.
            # alias_registry is a local variable — never global, never shared
            # between documents, passed explicitly to _apply_alias_resolution.
            alias_registry: Dict[str, str] = {}
            try:
                raw_text = await asyncio.to_thread(
                    self.parser.get_alias_window, file_path
                )
                if raw_text:
                    alias_window = _extract_alias_window(raw_text)
                    alias_registry = _build_alias_registry(alias_window, self.agent.llm)
            except Exception as e:
                print(f"   ⚠️ Alias pre-pass failed (continuing without it): {e}")

            # Parse — offloaded to thread so event loop stays free
            chunks = await asyncio.to_thread(self.parser.parse_with_metadata, file_path)
            print(f"   - Parsed {len(chunks)} chunks (Smart Layout)")

            if not chunks:
                return "empty_file"

            if cancellation_token():
                return "cancelled"

            # ── Phase A: Batch vector insert ──────────────────────────────────
            batch_size = 20
            vector_errors = 0
            for batch_start in range(0, len(chunks), batch_size):
                batch = chunks[batch_start:batch_start + batch_size]
                texts = [c["text"] for c in batch]
                metadatas = [{**c["metadata"], "source": filename} for c in batch]
                try:
                    self.vector_db.add_documents(
                        texts=texts,
                        metadatas=metadatas,
                        filename=filename
                    )
                except Exception as e:
                    print(f"   ⚠️ Vector batch error at chunk {batch_start}: {e}")
                    vector_errors += 1

            if vector_errors:
                print(f"   ⚠️ {vector_errors} vector batch(es) failed — partial index")

            print(f"   ✅ Vector insert complete ({len(chunks)} chunks, {vector_errors} errors)")

            if cancellation_token():
                await self.cleanup(filename)
                return "cancelled"

            # ── Phase B: Graph extraction (concurrent, LLM-driven) ────────────
            all_graphs = []

            async def extract_graph_safe(i, chunk):
                async with self.semaphore:
                    if cancellation_token():
                        return
                    await self._extract_graph_for_chunk(i, chunk, filename,
                                                        cancellation_token, all_graphs)

            tasks = [extract_graph_safe(i, chunk) for i, chunk in enumerate(chunks)]
            await asyncio.gather(*tasks)

            if cancellation_token():
                await self.cleanup(filename)
                return "cancelled"

            # ── Phase C: Alias resolution → Entity registry → bulk graph write ─
            if all_graphs:
                try:
                    # Step C1: deterministic alias resolution (before entity dedup)
                    # Replaces "Target" → "Vantage Systems, Inc." so the entity
                    # registry never sees them as separate nodes to cluster.
                    if alias_registry:
                        all_graphs = _apply_alias_resolution(all_graphs, alias_registry)

                    # Step C2: entity registry (rapidfuzz + nameparser + LLM dedup)
                    all_graphs = self.agent.apply_entity_registry(all_graphs)

                    # Step C3: bulk Neo4j write
                    self.kb.ingest_graph(all_graphs, filename)

                    # Step C4: MERGED_INTO provenance edges
                    # Must run AFTER ingest_graph() so MATCH finds existing nodes.
                    # Uses the registries stored by apply_entity_registry().
                    # Each entry wrapped individually so one failure never
                    # aborts the rest.
                    auto_reg = self.agent.last_auto_registry
                    llm_reg  = self.agent.last_llm_registry
                    full_reg = {**auto_reg, **llm_reg}
                    for absorbed, canonical in full_reg.items():
                        # Check source BEFORE merging dicts to avoid shadow bug
                        method = "rapidfuzz" if absorbed in auto_reg else "llm"
                        try:
                            self.kb.ingest_merged_into(
                                absorbed_name=absorbed,
                                canonical_name=canonical,
                                method=method,
                                score=85.0 if method == "rapidfuzz" else 0.0,
                                evidence=[f"auto_merged_from_{method}"],
                                confidence="confirmed"
                            )
                        except Exception as e:
                            logger.warning(
                                "MERGED_INTO provenance failed %s→%s: %s",
                                absorbed, canonical, e
                            )
                except Exception as e:
                    print(f"   ⚠️ Graph bulk write failed for {filename}: {e}")
                    print(f"   ℹ️ Vectors indexed successfully. Re-ingest to rebuild graph.")

            status = "completed_partial" if vector_errors else "completed"
            print(f"✅ Finished {filename}! Status: {status}")
            return status

        except Exception as e:
            print(f"   ❌ Fatal error for {filename}: {e}")
            await self.cleanup(filename)
            return f"failed: {e}"

    async def _extract_graph_for_chunk(self, i: int, chunk: Dict, filename: str,
                                        cancellation_token, all_graphs: List):
        text = chunk["text"]
        metadata = chunk["metadata"]
        page_num = metadata.get("page", 1)
        chunk_id = f"{filename}::chunk_{i}::page_{page_num}"

        try:
            # Ollama Redis inference lock removed — all providers are now cloud API.
            # Concurrency is governed by self.semaphore in extract_graph_safe above.
            graph = await self._call_with_retry(
                self.agent.extract_relationships, text, chunk_id, filename
            )

            if graph.get("nodes"):
                all_graphs.append(graph)

        except Exception as e:
            print(f"      ⚠️ Chunk {i} Graph error: {e}")
