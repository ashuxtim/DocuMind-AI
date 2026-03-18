import os
import json
import re
import hashlib
from functools import lru_cache
from typing import TypedDict, List, Dict

from langgraph.graph import StateGraph, END
from sentence_transformers import CrossEncoder

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
CALC_PATTERN = re.compile(
    r'([\$€£]?\s*[\d,]+\.?\d*\s*[MBK%]?)'   # left operand
    r'\s*[-+*/×÷]\s*'                          # operator
    r'([\$€£]?\s*[\d,]+\.?\d*\s*[MBK%]?)'    # right operand
    r'\s*=\s*'
    r'([\$€£]?\s*[\d,]+\.?\d*\s*[MBK%]?)',    # result
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
    print("⏳ Loading Reranker (Cross-Encoder)...")
    _reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
    print("✅ Reranker Ready.")
    services = {
        "vector_db":          VectorStore(),
        "kb":                 KnowledgeBase(),
        "llm":                _llm,
        "math_executor":      MathExecutor(_llm),
        "graph_builder":      get_graph_builder(),
        "constraint_checker": ConstraintChecker(_llm),
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


# ---------------------------------------------------------------------------
# NODE: decompose_query_node
# ---------------------------------------------------------------------------

def decompose_query_node(state: AgentState):
    """
    Breaks complex questions into simpler sub-queries for better retrieval.
    Uses word-boundary regex patterns + word-count to avoid false positives
    on common words like 'and', 'first', 'second'.
    """
    svc = get_services()
    llm = svc["llm"]

    question = state["question"]
    print("--- 🔀 DECOMPOSING QUERY ---")

    is_complex = (
        len(question.split()) > 15
        or any(re.search(p, question.lower()) for p in COMPLEXITY_PATTERNS)
    )

    if not is_complex:
        print("   💡 Simple question — no decomposition needed")
        return {"sub_queries": [question]}

    system_prompt = """You are a query decomposition expert.
Break complex questions into 2-4 simpler sub-questions.
Each sub-question should be answerable independently.

Return ONLY a JSON array of strings.
Example: ["What is revenue in Q1?", "What is revenue in Q2?", "What is the trend?"]
"""

    prompt = f"""Break this question into simpler sub-questions:

{question}

JSON array:"""

    try:
        response = llm.generate(prompt, system_prompt)
        sub_queries = _parse_json_list(response)

        if sub_queries:
            print(f"   ✅ Decomposed into {len(sub_queries)} sub-queries:")
            for i, sq in enumerate(sub_queries, 1):
                print(f"      {i}. {sq}")
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
    """
    svc = get_services()
    vector_db     = svc["vector_db"]
    kb            = svc["kb"]
    graph_builder = svc["graph_builder"]
    reranker      = svc["reranker"]

    sub_queries   = state.get("sub_queries", [state["question"]])
    question      = state["question"]
    selected_docs = state.get("selected_docs", [])

    print(f"--- 🔍 RETRIEVING FOR {len(sub_queries)} SUB-QUERIES ---")

    # Build filters for user-selected documents.
    # VectorStore.search() detects isinstance(value, list) → MatchAny(any=value)
    search_filters = {"source": selected_docs} if selected_docs else None

    # --- 1. VECTOR SEARCH (per sub-query) ---
    all_vector_results = []

    if len(sub_queries) > 1:
        per_query_limit = max(3, 10 // len(sub_queries))
        print(f"   📊 Multi-query mode: {per_query_limit} docs per sub-query")

        for i, sq in enumerate(sub_queries, 1):
            results = vector_db.search(sq, limit=per_query_limit, filters=search_filters)
            for r in results:
                r['_from_subquery'] = i
            all_vector_results.extend(results)
    else:
        results = vector_db.search(sub_queries[0], limit=10, filters=search_filters)
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

    # --- 3. RERANK (Cross-Encoder against original question) ---
    top_score = 0.0
    if unique_results:
        try:
            print("   ⚖️  Reranking candidates...")
            pairs = [[question, r['text']] for r in unique_results]
            scores = reranker.predict(pairs)

            for i, res in enumerate(unique_results):
                res['_rerank_score'] = scores[i]

            unique_results.sort(key=lambda x: x['_rerank_score'], reverse=True)

            MIN_RELEVANCE_SCORE = 0.35
            filtered = [r for r in unique_results if r['_rerank_score'] > MIN_RELEVANCE_SCORE]

            if not filtered:
                print(f"   ⚠️ No docs above threshold {MIN_RELEVANCE_SCORE} "
                      f"(best: {unique_results[0]['_rerank_score']:.2f})")
                filtered = unique_results[:3]

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

    if entities:
        graph_context = kb.query_subgraph(entities)
        if graph_context:
            docs.insert(0, f"--- RELEVANT GRAPH CONNECTIONS ---\n{graph_context}")
            print(f"   🧠 Graph context added ({len(graph_context)} chars)")
        else:
            print(f"   ℹ️ No graph context found for entities: {entities}")
    else:
        print("   ℹ️ No entities extracted — skipping graph search")

    return {
        "documents":        docs,
        "sources":          list(set(sources)),
        "top_rerank_score": top_score,
    }


# ---------------------------------------------------------------------------
# NODE: generate_node
# ---------------------------------------------------------------------------

def generate_node(state: AgentState):
    """
    Detects math, executes code, injects result into LLM context, then
    generates the answer using up to 60K chars of context (Qwen3-32B: 128K).
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
    if math_executor.needs_math(question) and not feedback:
        print("   🧮 Math question detected — running code execution...")
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
                print(f"   ⚠️ Code execution failed/skipped: "
                      f"{math_result.get('error') if math_result else 'Unknown'}")
        except Exception as e:
            print(f"   ⚠️ Math Executor Exception: {e}")

    # --- 2. SMART CONTEXT PRUNING ---
    # Qwen3-32B: 128K tokens ≈ 96,000 chars.
    # 60,000 leaves headroom for system prompt, history, and response.
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
    system_prompt = f"""You are DocuMind, an expert financial document assistant.

INSTRUCTION PRIORITY (highest to lowest):
1. 🔒 VERIFIED CALCULATIONS: If you see [SYSTEM NOTE: TRUSTED CODE EXECUTION RESULT], you MUST use that exact value. Do not recalculate mentally.
2. 🔄 AUDIT CORRECTIONS: {feedback_instruction if feedback else "No corrections needed."}
3. ⚠️ GRAPH OVERRIDES: If graph shows "REVISED_TO" or "CONTRADICTS", the FINAL value in the chain is truth.
4. 📄 DOCUMENT EVIDENCE: Use context below for all other facts.

OUTPUT RULES:
- Cite sources as [Source: filename, Page X]
- If answer not in context, say "The documents provided do not contain this information"
- If asked to calculate and no code result exists, say "I need to perform a calculation but code execution was not triggered"
- Be concise — no unnecessary preamble

DO NOT:
- Apologize or explain your reasoning process
- Guess numbers not in the text
- Ignore the verified calculation results
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

    response = llm.generate(prompt=user_prompt, system_prompt=system_prompt)
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
        for calc_tuple in answer_calcs:
            calc_variations = [
                f"{calc_tuple[0]}-{calc_tuple[1]}={calc_tuple[2]}",
                f"{calc_tuple[0]} - {calc_tuple[1]} = {calc_tuple[2]}",
            ]
            if not any(var in context for var in calc_variations):
                violations.append(
                    f"Invented calculation: '{calc_tuple[0]}-{calc_tuple[1]}={calc_tuple[2]}' not shown in source"
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
      Stage 3 (LLM)          — hallucination audit (only reached if 1+2 pass).

    Pre-audit shortcut saves ~0.6 LLM calls per query on average.
    """
    svc = get_services()
    llm                = svc["llm"]
    constraint_checker = svc["constraint_checker"]

    print("--- 🕵️ AUDITING ANSWER ---")
    question = state["question"]
    answer   = state["generation"]

    if "I don't know" in answer or "not found" in answer.lower():
        return {"audit_feedback": ""}

    all_docs = state["documents"]
    # Full context for fabrication detection — auditor must see all evidence
    full_context  = "\n".join(all_docs)
    # Trimmed context for LLM audit call — keeps prompt within budget
    audit_context = "\n".join(all_docs[:5])

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

    # --- STAGE 3: STANDARD LLM HALLUCINATION AUDIT ---
    # Only reached when fabrication pre-check passes AND no constraint violations.
    # ~60-70% of clean answers never reach this stage.
    print("   🔍 Running full LLM audit...")
    auditor_system_prompt = """You are a Strict Quality Control Auditor.
Check the 'Answer' against the 'Context'.

PASS CRITERIA:
1. Does the answer hallucinate numbers not in the text?
2. Does the answer mix up dates (e.g., Q1 vs Q2)?
3. Does the answer fabricate explanations using phrases like "due to" or "because"
   that don't appear in the context?
4. Does the answer invent arithmetic calculations not shown in the text?
   EXCEPTION: If the answer contains [SYSTEM NOTE: TRUSTED CODE EXECUTION RESULT],
   arithmetic steps derived from it are verified — do NOT flag them as fabrication.

If PASS: Return exactly "PASS".
If FAIL: Return a concise description of the error.
"""

    user_prompt = f"""
--- CONTEXT SNIPPET ---
{audit_context[:2000]}

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

workflow.add_node("decompose", decompose_query_node)
workflow.add_node("retrieve",  retrieve_node)
workflow.add_node("generate",  generate_node)
workflow.add_node("audit",     audit_node)

workflow.set_entry_point("decompose")
workflow.add_edge("decompose", "retrieve")
workflow.add_edge("retrieve",  "generate")
workflow.add_edge("generate",  "audit")

workflow.add_conditional_edges(
    "audit",
    decide_next_step,
    {"retry": "generate", "end": END}
)

app_graph = workflow.compile()