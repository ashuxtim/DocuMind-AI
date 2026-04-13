import os
import json
import re
import hashlib
import requests
from functools import lru_cache
from typing import TypedDict, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from langgraph.graph import StateGraph, END

from code_executor import MathExecutor
from vector_store import VectorStore
from knowledge_graph import KnowledgeBase
from llm_provider import get_llm_provider
from graph_agent import get_graph_builder
from constraint_checker import ConstraintChecker

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _parse_json_list(response: str) -> list:
    """
    Robustly extract a JSON array from an LLM response.
    Handles markdown code fences, preamble text, and trailing notes.
    Consistent with graph_agent.py and constraint_checker.py.
    """
    clean = re.sub(r'```(?:json)?', '', response).strip()
    match = re.search(r'\[.*?\]', clean, re.DOTALL)
    if not match:
        return []
    try:
        result = json.loads(match.group())
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        return []


# Compiled once at module load — used by detect_fabricated_explanations.
# Handles integers AND decimals/currency/units: $1.5M + $2.3M = $3.8M
# Group 1: left operand, Group 2: operator, Group 3: right operand, Group 4: result
CALC_PATTERN = re.compile(
    r'([\$€£]?\s*[\d,]+\.?\d*\s*[MBK%]?)'   # left operand  (group 1)
    r'\s*([-+*/×÷])\s*'                        # operator      (group 2)
    r'([\$€£]?\s*[\d,]+\.?\d*\s*[MBK%]?)'    # right operand (group 3)
    r'\s*=\s*'
    r'([\$€£]?\s*[\d,]+\.?\d*\s*[MBK%]?)',    # result        (group 4)
    re.IGNORECASE
)

# Common-knowledge arithmetic constants — never flagged as "invented numbers".
# 90 days/quarter, 365 days/year, 12 months/year, 100 for %, 30 days/month,
# 360 (banking year), 24 hours/day, 60 minutes/hour.
COMMON_KNOWLEDGE_CONSTANTS = {90, 365, 12, 100, 0.01, 30, 360, 24, 60}

# Calculation-intent words — if the question contains any of these, the user
# is explicitly requesting arithmetic on document values.
CALC_INTENT_WORDS = re.compile(
    r'\b(calculate|compute|multiply|divide|model|project|estimate|'
    r'what\s+is\s+\S+\s+percent\s+of|derive|total|sum|subtract|add|ratio)\b',
    re.IGNORECASE
)

# Regex patterns for complexity detection — word-boundary safe.
# Replaces the broad substring list that false-fired on "and", "first", etc.
COMPLEXITY_PATTERNS = [
    r'\bcompare\b',
    r'\btrend\b',
    r'\breconcile\b',
    r'\bderive\b',
    r'\bcalculate\b',
    r'\bacross\b',
    r'\bbetween\b',
    r'\bmultiple\b',
    r'\bq[1-4]\b.*\bq[1-4]\b',                              # Two quarters mentioned together
    r'\b(first|second|third).*(then|after|subsequently)\b', # Sequential steps
]

# Predicate/constraint signals — route to ConstraintChecker.
# Deliberately tight: operators and formal obligation keywords only.
# Plain English "all", "every", "exists" excluded — too broad, false positive factory.
PREDICATE_SIGNALS = re.compile(
    r'\bmust\b|\bshall\b|shall\s+not\b|cannot\b|required\s+to\b|'
    r'forall\s*\(|∀|∃|'
    r'>=|<=|!=|==|>(?!=)|<(?!=)',
    re.IGNORECASE
)

# Synthesis signals — multi-section questions that need min 3 sub-questions.
SYNTHESIS_SIGNALS = [
    r'\blist\s+(all|every|each)\b',
    r'\b(all|every|each)\s+\w+\s+(of|from|across|in)\b',
    r'\b(three|four|five|multiple)\b.{0,40}\b(commitment|payment|condition|person|risk)\b',
    r'\bseparate\b.{0,30}\b(amount|figure|value|payment)\b',
    r'\bacross\b.{0,30}\b(section|document|report)\b',
    r'\btotal.{0,20}(all|each|every)\b',
]

# Multi-entity signals — widen retrieval top-K when question targets 2+ entities.
MULTI_ENTITY_SIGNALS = [
    r'\b(both|two|three|four)\b.{0,40}\b(executive|person|employee|team|party|parties|director|shareholder)\b',
    r'\beach\s+of\b',
    r'\bthe\s+signatories\b',
    r'\beither\s+party\b',
    r'\ball\s+(three|four|named|listed)\b',
    r'\bwho\s+are\s+(the|all)\b',
]


# ---------------------------------------------------------------------------
# NVIDIA NIM RERANKER
# ---------------------------------------------------------------------------

def _is_retryable_reranker(exc: Exception) -> bool:
    """
    Retry on transient network failures and 429/5xx HTTP errors only.
    400 Bad Request (malformed payload) fails immediately — it will never
    succeed on retry. Same principle as _is_retryable_gemini in llm_provider.py.
    status_code lives on exc.response.status_code for requests.HTTPError.
    """
    if isinstance(exc, (requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        status = getattr(exc.response, 'status_code', None)
        return status == 429 or (status is not None and status >= 500)
    return False


class NvidiaReranker:
    """
    Thin wrapper around the NVIDIA NIM reranker REST API.
    Exposes a predict(pairs) method with the same interface as CrossEncoder.predict()
    so retrieve_node requires no changes.

    IMPORTANT — response format: the API returns a `rankings` list sorted by
    relevance (descending logit), where each item carries the *original* passage
    index. A naive loop reading response order assigns scores to wrong documents.
    predict() reconstructs a flat scores array keyed by original index so that
    scores[i] is always the logit for passage i.

    Scores are raw logits (not sigmoid-scaled). Threshold in retrieve_node is
    controlled by AGENT_MIN_RERANK_SCORE env var (default -5.0).
    Verified from NVIDIA NIM docs: relevant docs score roughly -3 to +1,
    clear noise drops below -5.
    """

    @property
    def ENDPOINT(self):
        model = os.getenv("RERANK_MODEL", "nvidia/llama-nemotron-rerank-1b-v2")
        return f"https://ai.api.nvidia.com/v1/retrieval/{model}/reranking"

    def __init__(self, api_key: str):
        if not api_key:
            raise RuntimeError(
                "NVIDIA_API_KEY is required for the reranker. "
                "Set NVIDIA_API_KEY in your K8s secret."
            )
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception(_is_retryable_reranker)
    )
    def predict(self, pairs: list) -> list:
        """
        pairs: list of [query, passage] — same format as CrossEncoder.predict().
        Returns: list of logit scores, scores[i] corresponds to pairs[i].
        """
        query = pairs[0][0]  # All pairs share the same query
        passages = [{"text": p[1]} for p in pairs]

        payload = {
            "model": os.getenv("RERANK_MODEL", "nvidia/llama-nemotron-rerank-1b-v2"),
            "query": {"text": query},
            "passages": passages,
        }

        response = requests.post(self.ENDPOINT, headers=self.headers, json=payload, timeout=(5, 30))
        response.raise_for_status()
        data = response.json()

        # Reconstruct flat scores array by original index.
        # API returns rankings sorted by relevance — each item has 'index' (original
        # passage position) and 'logit'. Reading in response order would assign
        # wrong scores to wrong documents.
        scores = [0.0] * len(pairs)
        for ranking in data["rankings"]:
            scores[ranking["index"]] = ranking["logit"]

        return scores


# ---------------------------------------------------------------------------
# SERVICE SINGLETON  (lru_cache — created once per worker process)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_services() -> dict:
    """
    Instantiates all heavy services exactly once per worker process.
    lru_cache guarantees single creation even under concurrent imports.
    Deferred until first request — FastAPI /health responds before
    Neo4j/Qdrant connections are established (avoids crash-loop on startup).
    """
    print("⏳ Initializing agent services (once per worker process)...")
    _llm = get_llm_provider()
    print("⏳ Initializing Reranker (NVIDIA NIM llama-nemotron-rerank-1b-v2)...")
    _reranker = NvidiaReranker(api_key=os.getenv("NVIDIA_API_KEY"))
    print("✅ Reranker Ready.")
    _audit_llm = get_llm_provider(role="audit")
    services = {
        "vector_db":          VectorStore(),
        "kb":                 KnowledgeBase(),
        "llm":                _llm,
        "audit_llm":          _audit_llm,
        "math_executor":      MathExecutor(get_llm_provider(role="extraction")),
        "graph_builder":      get_graph_builder(),
        "constraint_checker": ConstraintChecker(_audit_llm),
        "reranker":           _reranker,
    }
    print("✅ Agent services ready")
    return services


# ---------------------------------------------------------------------------
# STATE DEFINITION
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    question:          str
    history:           List[Dict[str, str]]
    sub_queries:       List[str]
    documents:         List[str]          # Context chunks (strings)
    generation:        str                # LLM answer
    audit_feedback:    str                # Error message from auditor (if any)
    retry_count:       int                # Prevents infinite loops
    sources:           List[str]          # Filenames used
    selected_docs:     List[str]          # User-selected docs for filtered search
    top_rerank_score:  float              # Best reranker score from retrieve_node
    has_contradiction: bool               # True when a documented conflict is found
    question_type:     str                # "math" | "predicate" | "factual" | "synthesis"
    multi_entity:      bool               # True when question targets 2+ entities


# ---------------------------------------------------------------------------
# NODE: route_question_node
# ---------------------------------------------------------------------------

def _llm_classify_question(question: str) -> tuple[str, bool]:
    """
    Use dedicated router LLM to classify question type.
    Returns (question_type, multi_entity).
    Falls back to regex on any failure.
    """
    print(f"   🧭 Router LLM classifying question...")
    try:
        router_llm = get_llm_provider(role="router")
        system_prompt = """You are a question classifier for a document Q&A system.
Classify the question into EXACTLY ONE of these types:

- math: requires arithmetic calculation on numbers extracted from documents
  (e.g. "what is the total of X plus Y", "calculate the difference between")
  NOT math: questions that merely ASK ABOUT a percentage or number stored in a document
- predicate: asks to compare, rank, or evaluate which of multiple options is better/worse/highest/lowest
- synthesis: requires combining information from multiple sections or documents,
  or asks for a comprehensive overview / summary
- factual: specific fact lookup, definition, or retrieval from a single location

Also output multi_entity as true if the question asks about 3 or more distinct
named entities simultaneously, otherwise false.

Respond in this EXACT format with no other text:
type: <math|predicate|synthesis|factual>
multi_entity: <true|false>"""

        user_prompt = f"Question: {question}"
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                router_llm.generate,
                user_prompt,
                system_prompt,
                20,
            )
            response = future.result(timeout=20)
        raw = response.strip().lower()
        lines = {line.split(":")[0].strip(): line.split(":", 1)[1].strip()
                 for line in raw.splitlines() if ":" in line}
        q_type = lines.get("type", "factual")
        if q_type not in ("math", "predicate", "synthesis", "factual"):
            q_type = "factual"
        multi = lines.get("multi_entity", "false") == "true"
        print(f"   🧭 Router LLM result: type={q_type}, multi_entity={multi}")
        return q_type, multi
    except Exception as e:
        print(f"   ⚠️ Router LLM failed ({e}), falling back to regex")
        return None, None


def route_question_node(state: AgentState):
    """
    Classifies the question before decomposition and retrieval.
    Sets question_type and multi_entity in AgentState — both fields survive
    the full cycle (route → decompose → retrieve → generate → audit).

    question_type:
      "math"      — calculation signal detected (reuses math_executor.needs_math())
                    → ConstraintChecker skipped in audit_node
      "synthesis" — multi-section question needing 3+ sub-questions
                    → ConstraintChecker skipped, decompose enforces min 3
      "predicate" — formal constraint language detected
                    → ConstraintChecker runs
      "factual"   — everything else
                    → ConstraintChecker skipped

    multi_entity: True when question signals 2+ named entities.
      → retrieve_node widens top-K from 10 to 15.

    Does NOT change graph edges — flow is always:
      route → decompose → retrieve → generate → audit
    """
    svc = get_services()
    math_executor = svc["math_executor"]

    question = state["question"]
    q_lower  = question.lower()

    print("--- 🧭 ROUTING QUESTION ---")

    # Try LLM router first
    question_type, multi_entity = _llm_classify_question(question)

    if question_type is None:
        # LLM failed — fall back to regex heuristics
        print("   🔄 Using regex fallback for classification")
        if math_executor.needs_math(question):
            question_type = "math"
        elif PREDICATE_SIGNALS.search(question):
            question_type = "predicate"
        elif any(re.search(p, q_lower) for p in SYNTHESIS_SIGNALS):
            question_type = "synthesis"
        else:
            question_type = "factual"
        multi_entity = any(re.search(p, q_lower) for p in MULTI_ENTITY_SIGNALS)

    print(f"   📄 Classified as: {question_type}"
          f"{' (multi-entity)' if multi_entity else ''}")

    return {
        "question_type": question_type,
        "multi_entity":  multi_entity,
    }


# ---------------------------------------------------------------------------
# NODE: decompose_query_node
# ---------------------------------------------------------------------------

def decompose_query_node(state: AgentState):
    """
    Breaks complex questions into simpler sub-queries for better retrieval.
    Uses word-boundary regex patterns + word-count to avoid false positives
    on common words like 'and', 'first', 'second'.

    Synthesis questions (question_type == "synthesis") enforce a minimum of
    3 sub-questions, each targeting a different section of the document.

    Commit A — synthesis min 3 sub-questions.
    Commit B — financial vocabulary guidance in decompose prompt.
    Both are included here. Attribution: Commit A = synthesis block,
    Commit B = financial vocabulary lines in system_prompt.
    """
    svc = get_services()
    llm = svc["audit_llm"]

    question      = state["question"]
    question_type = state.get("question_type", "factual")

    print("--- 🔀 DECOMPOSING QUERY ---")

    is_synthesis = question_type == "synthesis"

    is_complex = (
        is_synthesis
        or len(question.split()) > 15
        or any(re.search(p, question.lower()) for p in COMPLEXITY_PATTERNS)
    )

    if not is_complex:
        print("   💡 Simple question — no decomposition needed")
        return {"sub_queries": [question]}

    # --- Commit A: synthesis enforces min 3 section-targeted sub-questions ---
    if is_synthesis:
        system_prompt = """You are a query decomposition expert for document analysis.
This question requires synthesising information from MULTIPLE SECTIONS of the document.
Break it into 3-6 precise sub-questions where:
- Each sub-question targets a single fact, entity, or relationship
- Together they cover every component of the original question
- Each is independently answerable from the document
- Use concrete vocabulary likely to appear in the source document
- Include at least one sub-question targeting specific named entities
- Include at least one sub-question targeting a specific fact or value
Return ONLY a JSON array of sub-question strings. No explanation. No markdown.
Example: ["What is X?", "What is Y?", "How does X relate to Y?", "What value is associated with Z?"]
"""
    else:
        # --- Commit B: financial vocabulary guidance for all other complex questions ---
        system_prompt = """You are a query decomposition expert for document analysis.
Break this complex question into 2-4 simpler sub-questions where:
- Each sub-question is independently answerable from the document
- Together they fully address the original question
- Use concrete vocabulary likely to appear in the source document
Return ONLY a JSON array of sub-question strings. No explanation. No markdown.
Example: ["What is the value of X?", "What is the value of Y?", "What is the relationship between X and Y?"]
"""

    prompt = f"""Break this question into simpler sub-questions:

{question}

JSON array:"""

    try:
        response = llm.generate(prompt, system_prompt)
        sub_queries = _parse_json_list(response)

        # Enforce minimum 3 for synthesis — if LLM returned fewer, fall through
        # to single-query fallback which is better than under-decomposed synthesis
        if sub_queries and (not is_synthesis or len(sub_queries) >= 3):
            print(f"   ✅ Decomposed into {len(sub_queries)} sub-queries:")
            for i, sq in enumerate(sub_queries, 1):
                print(f"      {i}. {sq}")
            return {"sub_queries": sub_queries}

        if is_synthesis and sub_queries and len(sub_queries) < 3:
            print(f"   ⚠️ Synthesis question got only {len(sub_queries)} sub-queries — "
                  f"expected ≥3. Using what we have.")
            return {"sub_queries": sub_queries}

    except Exception as e:
        print(f"   ⚠️ Decomposition failed: {e}")

    # Fallback — treat as single query
    return {"sub_queries": [question]}


# ---------------------------------------------------------------------------
# NODE: retrieve_node
# ---------------------------------------------------------------------------

def retrieve_node(state: AgentState):
    """
    Retrieves for each sub-query, deduplicates, reranks, and optionally
    runs graph search when real entities are extracted.

    Multi-entity widening: when multi_entity is True, base_k raises from
    10 to 15 so per-sub-query limits cover both entity contexts.
    """
    svc = get_services()
    vector_db     = svc["vector_db"]
    kb            = svc["kb"]
    graph_builder = svc["graph_builder"]
    reranker      = svc["reranker"]

    sub_queries   = state.get("sub_queries", [state["question"]])
    question      = state["question"]

    # Always include the original question in the retrieval set.
    # Decomposed sub-queries often drop vocabulary from the original
    # (e.g. "retainers" → sub-query only says "bonuses"), causing
    # relevant chunks to be missed. The original question preserves
    # the full search vocabulary. Dedup on line 461 handles overlaps.
    if len(sub_queries) > 1 and question not in sub_queries:
        sub_queries = [question] + sub_queries

    selected_docs = state.get("selected_docs", [])
    multi_entity  = state.get("multi_entity", False)

    print(f"--- 🔍 RETRIEVING FOR {len(sub_queries)} SUB-QUERIES ---")

    # Build filters for user-selected documents.
    # VectorStore.search() detects isinstance(value, list) → MatchAny(any=value)
    search_filters = {"source": selected_docs} if selected_docs else None

    # --- 1. VECTOR SEARCH (per sub-query) ---
    all_vector_results = []

    # Multi-entity widening: base_k=15 ensures both entity contexts are covered
    # when sub-queries are distributed across entities. Tune via env var if needed.
    base_k = 15 if multi_entity else 10

    if len(sub_queries) > 1:
        per_query_limit = max(5, base_k // len(sub_queries))
        print(f"   📊 Multi-query mode: {per_query_limit} docs per sub-query"
              f"{' (multi-entity widened)' if multi_entity else ''}")

        def _search_subquery(args):
            idx, s_query = args
            try:
                res = vector_db.hybrid_search(s_query, limit=per_query_limit, filters=search_filters)
                for r in res:
                    r['_from_subquery'] = idx
                return res
            except Exception as e:
                print(f"   ⚠️ Search failed for sub-query {idx}: {e}")
                return []

        with ThreadPoolExecutor(max_workers=len(sub_queries)) as pool:
            futures = [pool.submit(_search_subquery, (i, sq)) for i, sq in enumerate(sub_queries, 1)]
            for future in as_completed(futures):
                all_vector_results.extend(future.result())
    else:
        results = vector_db.hybrid_search(sub_queries[0], limit=base_k, filters=search_filters)
        all_vector_results.extend(results)

    # --- 2. DEDUPLICATE (MD5 of first 200 chars — fast, whitespace-tolerant) ---
    seen_hashes = set()
    unique_results = []
    for res in all_vector_results:
        fingerprint = hashlib.md5(res['text'][:200].encode()).hexdigest()
        if fingerprint not in seen_hashes:
            seen_hashes.add(fingerprint)
            unique_results.append(res)

    print(f"   📦 {len(unique_results)} unique candidates from {len(sub_queries)} queries")

    # --- 3. RERANK (sub-query aware — each chunk scored against its own sub-query) ---
    # For multi-hop questions, scoring all chunks against the full composite question
    # causes cross-section chunks to score very low and get dropped. Instead, each
    # chunk is scored against the sub-query that retrieved it. A per-sub-query
    # minimum guarantee ensures all hops have context even when scores are low.
    # Chunks with no _from_subquery tag (single-query mode) fall back to full question.
    top_score = 0.0
    if unique_results:
        try:
            print("   ⚖️  Reranking candidates (sub-query aware)...")
            MIN_RELEVANCE_SCORE = float(os.getenv("AGENT_MIN_RERANK_SCORE", "-5.0"))

            # Score each chunk against its originating sub-query
            pairs = []
            for r in unique_results:
                sq_idx = r.get('_from_subquery', 0)
                if sq_idx and sq_idx <= len(sub_queries):
                    query_for_scoring = sub_queries[sq_idx - 1]
                else:
                    query_for_scoring = question
                pairs.append([query_for_scoring, r['text']])

            scores = reranker.predict(pairs)
            for i, res in enumerate(unique_results):
                res['_rerank_score'] = scores[i]

            unique_results.sort(key=lambda x: x['_rerank_score'], reverse=True)

            # Apply threshold filter
            filtered = [r for r in unique_results if r['_rerank_score'] > MIN_RELEVANCE_SCORE]

            # Per-sub-query minimum guarantee: ensure at least 1 doc per sub-query
            # survives even if its score is below threshold.
            # This prevents any single hop from being dropped entirely.
            guaranteed = {}
            for r in unique_results:
                sq_idx = r.get('_from_subquery', 0)
                if sq_idx and sq_idx not in guaranteed:
                    guaranteed[sq_idx] = r

            for sq_idx, doc in guaranteed.items():
                if doc not in filtered:
                    filtered.append(doc)
                    print(f"   📌 Sub-query {sq_idx} guaranteed 1 doc "
                          f"(score: {doc['_rerank_score']:.4f})")

            # Re-sort after guarantee insertions, then apply global cap
            filtered.sort(key=lambda x: x['_rerank_score'], reverse=True)

            if not filtered:
                print(f"   ⚠️ No docs survived (best: {unique_results[0]['_rerank_score']:.2f})")
                filtered = unique_results[:7]

            unique_results = filtered[:7]
            top_score = unique_results[0]['_rerank_score']
            print(f"   ✅ Kept {len(unique_results)} docs (top score: {top_score:.4f})")

        except Exception as e:
            print(f"   ⚠️ Reranking failed: {e}")
            unique_results = unique_results[:7]

    # --- 4. FORMAT RESULTS ---
    docs = []
    sources = []
    for res in unique_results:
        meta    = res.get('metadata', {})
        text    = res.get('text', '')
        source  = meta.get('source', 'Unknown')
        page    = meta.get('page', '?')
        section = meta.get('section', 'General')
        score   = res.get('_rerank_score', 0.5)

        docs.append(f"[Source: {source} | Section: {section} | Pg {page} | Score: {score:.2f}]\n{text}")
        sources.append(f"{source}:Pg{page}")

    # --- 5. GRAPH SEARCH (only when LLM extracted real entities) ---
    # Keyword fallback removed — firing Neo4j on every simple question adds noise.
    # Accepted regression: queries where entity extraction yields nothing skip graph.
    print("   🧠 Extracting entities for graph search...")
    entities = list(graph_builder.extract_query_entities(question))

    # Entity expansion: scan top retrieved chunks for answer-side entities
    # that never appear in the question text (e.g. "OCC" in a multi-hop question
    # that asks "which agency..." without naming it). This grounds the graph
    # query in what was actually retrieved rather than only what was asked.
    # Dynamic entity expansion — extract answer-side entities from top retrieved
    # chunks using the same LLM extractor. Domain-agnostic: works for any document
    # domain without hardcoded lists.
    if docs:
        chunk_sample = " ".join(docs[:4])[:2000]
        try:
            chunk_entities = list(graph_builder.extract_query_entities(chunk_sample))
            for ent in chunk_entities:
                if ent not in entities:
                    entities.append(ent)
            print(f"   🔍 Entity expansion: {len(chunk_entities)} candidates from chunks")
        except Exception:
            pass  # expansion is best-effort, never blocks retrieval

    if entities:
        print(f"   🧠 Graph entities (expanded): {entities}")
        graph_context = kb.query_subgraph(
            entities,
            source_filter=selected_docs if selected_docs else None,
        )
        if graph_context:
            docs.insert(0, f"--- RELEVANT GRAPH CONNECTIONS ---\n{graph_context}")
            print(f"   🧠 Graph context added ({len(graph_context)} chars)")
        else:
            print(f"   ℹ️ No graph context found for entities: {entities}")
    else:
        print("   ℹ️ No entities extracted — skipping graph search")

    return {
        "documents":        docs,
        "sources":          list({s: None for s in sources}.keys()),
        "top_rerank_score": top_score,
    }


# ---------------------------------------------------------------------------
# NODE: generate_node
# ---------------------------------------------------------------------------

def generate_node(state: AgentState):
    """
    Detects math, executes code, injects result into LLM context, then
    generates the answer using up to AGENT_MAX_CONTEXT_CHARS of context.
    Feedback from the auditor is injected into BOTH system and user turns.
    """
    svc = get_services()
    llm           = svc["llm"]
    math_executor = svc["math_executor"]

    print("--- ✍️ GENERATING ANSWER ---")
    question  = state["question"]
    documents = state["documents"]
    history   = state["history"]
    feedback  = state.get("audit_feedback", "")

    # --- 1. MATH EXECUTION ---
    math_context = ""
    question_type = state.get("question_type", "factual")
    if question_type == "math" and not feedback:
        print("   🧮 Math question detected (router classified) — running code execution...")
        raw_context = "\n\n".join(documents[:15])
        try:
            math_result = math_executor.process_math_question(question, raw_context)
            if math_result and math_result.get('success'):
                print(f"   ✅ Code Execution Success: {math_result['output']}")
                math_context = f"""
[SYSTEM NOTE: TRUSTED CODE EXECUTION RESULT]
The user asked for a calculation. A Python script verified this result:
CALCULATED VALUE: {math_result['output']}

MANDATORY INSTRUCTION: You must use this calculated value in your answer.
Do not attempt to recalculate it mentally.
"""
            else:
                reason = (math_result.get('error') or math_result.get('explanation', 'validation failed')
                          if math_result else 'execution returned no result')
                print(f"   ⚠️ Code execution failed/skipped: {reason}")
                print(f"   ↩️  Falling back to standard LLM generation")
        except Exception as e:
            print(f"   ⚠️ Math Executor Exception: {e}")

    # --- 2. SMART CONTEXT PRUNING ---
    # Maximum chars of document context passed to the LLM.
    # Default 60K is safe for all providers including Groq (Qwen3-32B: ~24K char budget).
    # Increase via AGENT_MAX_CONTEXT_CHARS for providers with larger context windows:
    #   NVIDIA nemotron-super (NIM API cap 256K tokens): up to ~190K chars
    #   Anthropic Sonnet 4.5 (200K tokens):              up to ~150K chars
    #   Gemini 2.5 Flash (1M tokens):                    up to ~750K chars
    #   Groq Qwen3-32B (32K tokens):                     do not exceed ~20K chars
    MAX_CHARS = int(os.getenv("AGENT_MAX_CONTEXT_CHARS", "60000"))
    current_chars = len(question) + len(math_context)

    history_text = ""
    if history:
        recent_history = history[-2:]
        history_text = "\n".join(
            [f"{m.get('role', 'user').upper()}: {m.get('content', '')}" for m in recent_history]
        )
        current_chars += len(history_text)

    graph_docs  = [d for d in documents if "GRAPH CONNECTIONS" in d]
    vector_docs = [d for d in documents if "GRAPH CONNECTIONS" not in d]

    allowed_docs = []
    for doc in vector_docs:
        if current_chars + len(doc) < MAX_CHARS - 2000:  # Reserve 2K for graph + response
            allowed_docs.append(doc)
            current_chars += len(doc)
        else:
            print(f"   ✂️ Context limit reached at {len(allowed_docs)} docs ({current_chars} chars).")
            break

    graph_text   = graph_docs[0] if graph_docs else ""
    context_text = f"{graph_text}\n\n{chr(10).join(allowed_docs)}" if allowed_docs else "No relevant context."

    # --- 3. FEEDBACK INJECTION ---
    feedback_instruction = ""
    if feedback:
        print(f"   ⚠️ RETRYING WITH FEEDBACK: {feedback}")
        feedback_instruction = f"""
PREVIOUS ANSWER WAS REJECTED.
ERROR: {feedback}
INSTRUCTION: Fix the error described above. Do NOT apologize.
"""

    # Feedback injected into system prompt (priority signal) AND user prompt
    # (user turn has higher attention weight in instruction-tuned models).
    system_prompt = f"""You are DocuMind, an expert document assistant.

INSTRUCTION PRIORITY (highest to lowest):
1. 🔒 VERIFIED CALCULATIONS: If you see [SYSTEM NOTE: TRUSTED CODE EXECUTION RESULT], you MUST use that exact value. Do not recalculate mentally.
2. 🔄 AUDIT CORRECTIONS: {feedback_instruction if feedback else "No corrections needed."}
3. ⚠️ GRAPH OVERRIDES: If graph shows "REVISED_TO" or "CONTRADICTS", the FINAL value in the chain is truth.
4. 🔗 GRAPH CONNECTIONS: Facts stated as (Entity A) -[RELATIONSHIP]-> (Entity B) in the
   "--- RELEVANT GRAPH CONNECTIONS ---" section are extracted directly from the source
   documents and are fully trusted. Use them to answer questions about relationships,
   origins, authority, and entity connections.
5. 📄 DOCUMENT EVIDENCE: Use document chunks in context for all other facts.

REASONABLE INFERENCE:
- When an entity is explicitly named in the context (document chunks or graph
  connections) alongside the subject of the question, you may state it is
  associated or connected — even if the context does not use the exact phrasing
  from the question.
- Do NOT upgrade weak contextual mentions to strong causal claims unless the
  context uses explicit causal language (established, created, enacted, granted,
  founded, authorised).
- You may only connect entities that appear together in the same passage or are
  linked in graph connections.
- This is NOT permission to fabricate causal relationships.

OUTPUT RULES:
Format your answer using markdown:
- Use ## for section headings when the answer has distinct sections
- Use **bold** for key terms, names, and numeric values
- Use bullet points (- ) for lists of items
- Use numbered lists (1.) for sequential steps or ranked items
- Keep paragraphs short — 2-3 sentences maximum

- Cite sources as [Source: filename, Page X] for document facts
- For graph-derived facts, cite as [Source: Knowledge Graph]
- Say "The documents provided do not contain this information" ONLY when the
  relevant entity or concept is completely absent from ALL provided context
  (both document chunks and graph connections). If the entity appears anywhere
  in context, answer using what is available.
- If asked to calculate and no code result exists, say "I need to perform a
  calculation but code execution was not triggered"
- Be concise — no unnecessary preamble

DO NOT:
- Apologize or explain your reasoning process
- Invent specific numbers, dates, or named entities not found in context
- Ignore the verified calculation results
- Treat graph connection facts as missing just because they are not in document text
- Fabricate relationships between entities that never appear together in context
"""

    user_prompt = f"""
--- PREVIOUS CONVERSATION ---
{history_text}

--- CONTEXT ---
{context_text}

{math_context}

{f"--- CORRECTION REQUIRED ---{chr(10)}{feedback_instruction}" if feedback else ""}

--- QUESTION ---
{question}
"""

    response = llm.generate(
        prompt=user_prompt,
        system_prompt=system_prompt,
        max_tokens=8192,
    )
    if not response or not response.strip():
        print("   ⚠️ WARNING: LLM returned empty response — check reasoning_content extraction")
        response = "ERROR: Generation returned empty. Please retry."
    return {"generation": response, "retry_count": state.get("retry_count", 0) + 1}


# ---------------------------------------------------------------------------
# FABRICATION DETECTION
# ---------------------------------------------------------------------------

def detect_fabricated_explanations(answer: str, context: str, question: str = "", has_math_result: bool = False) -> dict:
    """
    Detect if the answer fabricates causal explanations or arithmetic not in source.

    question parameter (optional): causal phrases that appeared in the question
    are not fabricated — the LLM correctly echoed them. Omitting this caused
    false positives (Q8 test failure).
    """
    violations = []

    causal_phrases = [
        "due to", "because of", "as a result of", "caused by",
        "owing to", "on account of", "thanks to", "attributable to"
    ]

    for phrase in causal_phrases:
        in_answer   = phrase in answer.lower()
        in_context  = phrase in context.lower()
        in_question = phrase in question.lower()  # Q8 fix: don't flag question language

        if in_answer and not in_context and not in_question:
            violations.append(f"Fabricated causal link: '{phrase}' not in source")

    # Arithmetic fabrication — skipped when math executor produced a verified result.
    # A code-executed answer by definition contains arithmetic not verbatim in source.
    if not has_math_result:
        answer_calcs = CALC_PATTERN.findall(answer)
        user_asked_calc = bool(CALC_INTENT_WORDS.search(question))

        for calc_tuple in answer_calcs:
            # Groups: (left_operand, operator, right_operand, result)
            left, op, right, result_val = calc_tuple

            # Fix A — generate variations for ALL operators, not just subtraction
            all_ops = ['-', '+', '*', '/', '×', '÷']
            calc_variations = []
            for try_op in all_ops:
                calc_variations.append(f"{left}{try_op}{right}={result_val}")
                calc_variations.append(f"{left} {try_op} {right} = {result_val}")

            # If the exact equation appears verbatim in context, it's not fabricated
            if any(var in context for var in calc_variations):
                continue

            # Fix B+C — check if both operands are individually sourced
            def _normalize_operand(raw: str) -> float:
                """Strip currency, commas, whitespace, MBK% suffixes → float."""
                s = re.sub(r'[\$€£,\s]', '', raw.strip())
                s = re.sub(r'[MBK%]$', '', s, flags=re.IGNORECASE)
                try:
                    return float(s)
                except ValueError:
                    return None

            left_num  = _normalize_operand(left)
            right_num = _normalize_operand(right)

            # Fix C — skip common-knowledge constants entirely
            left_is_constant  = left_num is not None and left_num in COMMON_KNOWLEDGE_CONSTANTS
            right_is_constant = right_num is not None and right_num in COMMON_KNOWLEDGE_CONSTANTS

            # Check whether each non-constant operand's raw text appears in context
            left_in_context  = left_is_constant or left.strip() in context
            right_in_context = right_is_constant or right.strip() in context

            # Fix B — if both operands are sourced/constant AND user asked for
            # a calculation, this is legitimate derived math, not fabrication
            if left_in_context and right_in_context and user_asked_calc:
                continue

            violations.append(
                f"Invented calculation: '{left}{op}{right}={result_val}' not shown in source"
            )

    return {
        "fabricated_explanations": any("causal" in v for v in violations),
        "invented_calculations":   any("calculation" in v for v in violations),
        "violations":              violations,
    }


# ---------------------------------------------------------------------------
# CONTRADICTION HELPER
# ---------------------------------------------------------------------------

def check_source_explains_contradiction(context: str) -> tuple:
    """
    Returns (is_explained: bool, explanation_type: str).

    explanation_type values:
      'documented_conflict' — document itself explicitly flags the inconsistency
                              (legal/M&A docs with NOTICE OF MATERIAL INCONSISTENCY etc.)
                              → Answer is CORRECT to describe both sides. Do NOT retry.
      'revision'            — document revises/corrects a value
                              → Use the corrected value.
      'none'                → Source does not explain the discrepancy.
                              → State this explicitly; do not invent an explanation.
    """
    context_lower = context.lower()

    # Type 1: explicitly flagged conflict in the document itself
    conflict_markers = [
        "notice of material inconsistency",
        "direct conflict between",
        "nca has identified",
        "conflict exists between",
        "must be reconciled",
        "does not explain this discrepancy",
        "readers are specifically advised",
        "must resolve this inconsistency",
    ]
    if any(marker in context_lower for marker in conflict_markers):
        return True, "documented_conflict"

    # Type 2: document revises or corrects a value
    revision_markers = [
        "revised to", "corrected to", "restated as", "superseded by",
        "amended to", "updated to", "replaced with", "should be",
        "actually is", "the correct value is", "error was", "mistake was",
    ]
    if any(marker in context_lower for marker in revision_markers):
        return True, "revision"

    return False, "none"


# ---------------------------------------------------------------------------
# NODE: audit_node
# ---------------------------------------------------------------------------

def audit_node(state: AgentState):
    """
    Multi-stage auditor:
      Stage 1 (fast, no LLM) — fabrication detection against ALL documents.
                               Returns immediately on violation — no LLM call.
      Stage 2 (constraint)   — logical predicate consistency check.
                               Runs ONLY for explicit predicate questions.
                               Skipped for factual/math/synthesis prompts where
                               omission is not a contradiction.
      Stage 3 (LLM)          — hallucination audit (only reached if 1+2 pass).

    Pre-audit shortcut saves ~0.6 LLM calls per query on average.
    """
    svc = get_services()
    llm                = svc["audit_llm"]
    constraint_checker = svc["constraint_checker"]

    print("--- 🕵️ AUDITING ANSWER ---")
    question      = state["question"]
    answer        = state["generation"]
    question_type = state.get("question_type", "factual")

    if "I don't know" in answer or "not found" in answer.lower():
        return {"audit_feedback": ""}

    all_docs = state["documents"]
    # Full context for fabrication detection AND audit — auditor must see all evidence
    full_context  = "\n".join(all_docs)
    audit_context = full_context

    # --- STAGE 1: FAST FABRICATION PRE-CHECK (no LLM cost) ---
    print("   ⚡ Running fast fabrication pre-check...")
    fabrication_check = detect_fabricated_explanations(
        answer, full_context, question,
        has_math_result="TRUSTED CODE EXECUTION RESULT" in state.get("generation", ""),
    )

    if fabrication_check['violations']:
        violation_msg = "; ".join(fabrication_check['violations'][:2])
        print(f"   ❌ Pre-check FAILED: {violation_msg}")
        return {
            "audit_feedback": (
                f"FABRICATION ERROR: {violation_msg}. "
                "Only use explanations and calculations that explicitly appear in the source text. "
                "If source doesn't explain a discrepancy, state 'The document provides no explanation.'"
            )
        }

    # --- STAGE 2: CONSTRAINT CHECKING ---
    # Run Stage 2 only for explicit predicate questions. Factual questions often
    # receive short, correct answers that need not restate every retrieved fact.
    # Treating omitted context as a constraint violation creates false retries and
    # wastes query budget.
    if question_type == "predicate":
        print("   🔍 Extracting logic constraints...")
        predicates = constraint_checker.extract_predicates(question, audit_context)

        if predicates:
            is_consistent, explanation = constraint_checker.check_consistency(predicates, audit_context)

            if not is_consistent:
                print(f"   ❌ INCONSISTENT: {explanation}")

                source_explains, explanation_type = check_source_explains_contradiction(full_context)

                if explanation_type == "documented_conflict":
                    # Document itself flags this conflict — answer is correct to describe both sides.
                    # Do NOT retry. Mark has_contradiction so main.py can signal the UI.
                    print("   ✅ DOCUMENTED CONFLICT — answer correctly describes flagged inconsistency")
                    return {"audit_feedback": "", "has_contradiction": True}

                elif explanation_type == "revision":
                    return {
                        "audit_feedback": (
                            f"CONTRADICTION DETECTED: {explanation}. "
                            "The source provides a revision — use the corrected value."
                        )
                    }
                else:
                    return {
                        "audit_feedback": (
                            f"UNRESOLVED CONTRADICTION: {explanation}. "
                            "The source does not explain this discrepancy. "
                            "State this explicitly — DO NOT INVENT an explanation."
                        )
                    }

            is_valid, violation = constraint_checker.validate_answer_against_constraints(answer, predicates)
            if not is_valid and not violation.startswith("VALIDATION_ERROR:"):
                print(f"   ❌ INVALID ANSWER: {violation}")
                return {"audit_feedback": f"Answer violates logic constraint: {violation}"}
    else:
        print(f"   ⏭️  Stage 2 skipped — question_type={question_type}")

    # --- STAGE 3: STANDARD LLM HALLUCINATION AUDIT ---
    # Only reached when fabrication pre-check passes AND no constraint violations.
    # ~60-70% of clean answers never reach this stage.
    print("   🔍 Running full LLM audit...")
    auditor_system_prompt = """You are a Strict Quality Control Auditor.
Check the 'Answer' against the 'Context'.
The Context contains two types of trusted evidence:
1. Document chunks — text extracted directly from source documents.
2. Graph connections — relationship facts extracted from the same documents,
   formatted as: (Entity A) -[RELATIONSHIP]-> (Entity B)
   These are equally valid as document text. Do NOT flag claims supported
   by graph connections as hallucination.

FAIL CRITERIA (flag these only):
1. Answer states a number that appears NOWHERE in document chunks OR graph connections.
   EXCEPTION: Common-knowledge arithmetic constants are not required to appear in the
   document — do NOT flag these as invented numbers. Common-knowledge constants include:
   90 (days per quarter), 365 (days per year), 12 (months per year),
   100 (percentage conversion), 30 (days per month), 360 (banking year days),
   24 (hours per day), 60 (minutes per hour).
2. Answer mixes up dates (e.g., Q1 vs Q2) contradicting the context.
3. Answer fabricates causal explanations using "due to" or "because" 
   that have no basis in either document chunks or graph connections.
4. Answer invents arithmetic calculations not shown anywhere in context.
   EXCEPTION 1: If the answer contains [SYSTEM NOTE: TRUSTED CODE EXECUTION RESULT],
   arithmetic steps derived from it are verified — do NOT flag them.
   EXCEPTION 2: If the user's question explicitly requests a calculation (contains
   words like calculate, compute, model, project, estimate, multiply, divide, derive,
   total, sum, ratio, or "what is X% of") AND both operand values are individually
   present in the document chunks or graph connections, the arithmetic is legitimate
   derived math — do NOT flag it. The user asked for this computation.

PASS if all claims in the answer are supported by OR reasonably inferable
from document chunks OR graph connections in the context.
A claim is "reasonably inferable" when the entities it references are
explicitly mentioned together in the same context passage or linked in
the graph — even if the exact phrasing differs from the question.
If PASS: Return exactly "PASS".
If FAIL: Return a concise description of what was fabricated and where.
"""

    user_prompt = f"""
--- CONTEXT SNIPPET ---
{audit_context[:15000]}

--- USER QUESTION ---
{question}

--- PROPOSED ANSWER ---
{answer}
"""

    audit_result = llm.generate(prompt=user_prompt, system_prompt=auditor_system_prompt)

    if "PASS" in audit_result.upper():
        print("   ✅ Audit PASSED")
        return {"audit_feedback": ""}
    else:
        print(f"   ⚠️ Audit feedback: {audit_result}")
        return {"audit_feedback": audit_result}


# ---------------------------------------------------------------------------
# CONDITIONAL EDGES
# ---------------------------------------------------------------------------

def decide_next_step(state: AgentState):
    """Retry if audit failed and retries remain, otherwise end."""
    feedback = state.get("audit_feedback", "")
    retries  = state.get("retry_count", 0)

    if feedback and retries < 2:
        return "retry"
    return "end"


# ---------------------------------------------------------------------------
# GRAPH ASSEMBLY
# ---------------------------------------------------------------------------

workflow = StateGraph(AgentState)

workflow.add_node("route",     route_question_node)
workflow.add_node("decompose", decompose_query_node)
workflow.add_node("retrieve",  retrieve_node)
workflow.add_node("generate",  generate_node)
workflow.add_node("audit",     audit_node)

workflow.set_entry_point("route")
workflow.add_edge("route",     "decompose")
workflow.add_edge("decompose", "retrieve")
workflow.add_edge("retrieve",  "generate")
workflow.add_edge("generate",  "audit")

workflow.add_conditional_edges(
    "audit",
    decide_next_step,
    {"retry": "generate", "end": END}
)

app_graph = workflow.compile()
