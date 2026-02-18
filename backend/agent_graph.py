import os
import json
import re
from typing import TypedDict, List, Annotated, Dict, Tuple
from langgraph.graph import StateGraph, END
from code_executor import MathExecutor
from sentence_transformers import CrossEncoder

# Import your existing system components
from vector_store import VectorStore
from knowledge_graph import KnowledgeBase
from llm_provider import get_llm_provider
from graph_agent import GraphBuilder
from constraint_checker import ConstraintChecker

# --- GLOBAL INSTANCES ---
vector_db = VectorStore()
kb = KnowledgeBase()
llm = get_llm_provider()
math_executor = MathExecutor(llm)
graph_builder = GraphBuilder()
constraint_checker = ConstraintChecker(llm)

print("⏳ Loading Reranker (Cross-Encoder)...")
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
print("✅ Reranker Ready.")

# --- STATE DEFINITION ---
class AgentState(TypedDict):
    question: str
    history: List[Dict[str, str]]
    sub_queries: List[str]
    documents: List[str]            # Context chunks
    generation: str                 # The LLM's answer
    audit_feedback: str             # Error msg from Auditor (if any)
    retry_count: int                # To prevent infinite loops
    sources: List[str]              # Filenames used

# --- NODES ---

def decompose_query_node(state: AgentState):
    """
    Breaks complex questions into simpler sub-queries for better retrieval.
    """
    question = state["question"]
    print(f"--- 🔀 DECOMPOSING QUERY ---")

    # Check if question is complex (needs decomposition)
    complexity_markers = [
        "and", "trend", "compare", "across", "between", "multiple",
        "calculate", "reconcile", "derive", "q1", "q2", "q3", "q4",
        "first", "second", "third", "then", "after", "before"
    ]

    is_complex = any(marker in question.lower() for marker in complexity_markers)

    if not is_complex:
        print("   💡 Simple question - no decomposition needed")
        return {"sub_queries": [question]}

    # Use LLM to decompose
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

        # Parse JSON
        import json
        clean = response.replace("```json", "").replace("```", "").strip()
        start = clean.find('[')
        end = clean.rfind(']') + 1

        if start != -1 and end > start:
            sub_queries = json.loads(clean[start:end])
            print(f"   ✅ Decomposed into {len(sub_queries)} sub-queries:")
            for i, sq in enumerate(sub_queries, 1):
                print(f"      {i}. {sq}")
            return {"sub_queries": sub_queries}
    
    except Exception as e:
        print(f"   ⚠️ Decomposition failed: {e}")

    # Fallback
    return {"sub_queries": [question]}

def retrieve_node(state: AgentState):
    """
    ENHANCED: Retrieves for EACH sub-query, then deduplicates and reranks.
    """
    sub_queries = state.get("sub_queries", [state["question"]])
    question = state["question"]

    print(f"--- 🔍 RETRIEVING FOR {len(sub_queries)} SUB-QUERIES ---")

    # 🆕 BALANCED retrieval - ensure each sub-query contributes
    all_vector_results = []
    
    if len(sub_queries) > 1:
        # Multi-query: get fewer per query to ensure balance
        per_query_limit = max(3, 10 // len(sub_queries))
        print(f"   📊 Multi-query mode: {per_query_limit} docs per sub-query")
        
        for i, sq in enumerate(sub_queries, 1):
            results = vector_db.search(sq, limit=per_query_limit)
            # Tag which sub-query this came from
            for r in results:
                r['_from_subquery'] = i
            all_vector_results.extend(results)
    else:
        # Single query: get more docs
        results = vector_db.search(sub_queries[0], limit=10)
        all_vector_results.extend(results)

    # 2. Deduplicate by text content
    seen_texts = set()
    unique_results = []
    for res in all_vector_results:
        text = res['text']
        if text not in seen_texts:
            seen_texts.add(text)
            unique_results.append(res)
    
    print(f"   📦 Collected {len(unique_results)} unique candidates from {len(sub_queries)} queries")

    # 3. Rerank with Cross-Encoder (against ORIGINAL question)
    if len(unique_results) > 0:
        try:
            print("   ⚖️  Reranking candidates...")
            docs_for_rerank = [r['text'] for r in unique_results]
            
            # Score against the MAIN question (not sub-queries) to ensure final relevance
            pairs = [[question, doc] for doc in docs_for_rerank]
            scores = reranker.predict(pairs)

            # Attach scores
            for i, res in enumerate(unique_results):
                res['_rerank_score'] = scores[i]

            # Sort descending
            unique_results.sort(key=lambda x: x['_rerank_score'], reverse=True)
            
            # 🆕 FILTER by minimum relevance threshold
            MIN_RELEVANCE_SCORE = 0.35  # Tune based on your reranker
            filtered_results = [r for r in unique_results if r['_rerank_score'] > MIN_RELEVANCE_SCORE]
            
            if not filtered_results:
                print(f"   ⚠️ No docs above threshold {MIN_RELEVANCE_SCORE} (best: {unique_results[0]['_rerank_score']:.2f})")
                # Take top 3 anyway if nothing passes (partial match scenario)
                filtered_results = unique_results[:3]
            
            # Keep Top 7 from filtered set
            unique_results = filtered_results[:7]
            print(f"   ✅ Kept {len(unique_results)} docs (top score: {unique_results[0]['_rerank_score']:.4f})")

        except Exception as e:
            print(f"   ⚠️ Reranking failed: {e}")
            unique_results = unique_results[:7]

    # 4. Format results - PRESERVE SCORES
    docs = []
    sources = []
    for res in unique_results:
        meta = res.get('metadata', {})
        text = res.get('text', '')
        source = meta.get('source', 'Unknown')
        page = meta.get('page', '?')
        section = meta.get('section', 'General')
        score = res.get('_rerank_score', 0.5)  # 🆕 Extract score
        
        # FIX: Store as string to match AgentState typing.
        docs.append(f"[Source: {source} | Section: {section} | Pg {page} | Score: {score:.2f}]\n{text}")
        sources.append(f"{source}:Pg{page}")

    # 5. Graph Search (Using Entity Extraction)
    print("   🧠 Extracting entities with LLM...")
    entities = graph_builder.extract_query_entities(question)
    keywords = entities if entities else [w for w in question.split() if len(w) > 4]

    graph_context = kb.query_subgraph(keywords)
    if graph_context:
        # FIX: Prepend graph context as a string so it is always at index 0
        docs.insert(0, f"--- RELEVANT GRAPH CONNECTIONS ---\n{graph_context}")

    return {"documents": docs, "sources": list(set(sources))}

def generate_node(state: AgentState):
    """
    ENHANCED: Detects math, executes code, and INJECTS result into LLM context.
    """
    print("--- ✍️ GENERATING ANSWER ---")
    question = state["question"]
    documents = state["documents"]
    history = state["history"]
    feedback = state.get("audit_feedback", "")
    
    # --- 1. MATH EXECUTION (CONTEXT INJECTION MODE) ---
    math_context = ""
    # Only run math if we haven't already failed an audit (to prevent loops)
    if math_executor.needs_math(question) and not feedback:
        print("   🧮 Math question detected - running code execution...")
        
        # Build temp context for the math engine (needs raw text)
        # We use top 15 docs to ensure we catch all variables
        raw_context = "\n\n".join(documents[:15])
        
        # Execute
        try:
            math_result = math_executor.process_math_question(question, raw_context)
            
            if math_result and math_result.get('success'):
                # SUCCESS: Inject the result into the LLM's brain
                print(f"   ✅ Code Execution Success: {math_result['output']}")
                math_context = f"""
                [SYSTEM NOTE: TRUSTED CODE EXECUTION RESULT]
                The user asked for a calculation. A Python script verified this result:
                CALCULATED VALUE: {math_result['output']}
                
                MANDATORY INSTRUCTION: You must use this calculated value in your answer. 
                Do not attempt to recalculate it mentally.
                """
            else:
                print(f"   ⚠️ Code execution failed/skipped: {math_result.get('error') if math_result else 'Unknown'}")
        except Exception as e:
            print(f"   ⚠️ Math Executor Exception: {e}")

    # --- 2. SMART CONTEXT PRUNING (SCORE-AWARE) ---
    MAX_CHARS = 12000 
    current_chars = len(question) + len(math_context)
    
    # Prune History first
    history_text = ""
    if history:
        recent_history = history[-2:] 
        history_text = "\n".join([f"{m.get('role', 'user').upper()}: {m.get('content', '')}" for m in recent_history])
        current_chars += len(history_text)

    # 🆕 FIX: Extract graph context safely (documents are now guaranteed strings)
    graph_docs = [d for d in documents if "GRAPH CONNECTIONS" in d]
    vector_docs = [d for d in documents if "GRAPH CONNECTIONS" not in d]
    
    # Add docs in existing order (already sorted by reranker) until limit
    allowed_docs = []
    for doc in vector_docs:
        if current_chars + len(doc) < MAX_CHARS - 500:  # Reserve space for graph
            allowed_docs.append(doc)
            current_chars += len(doc)
        else:
            print(f"   ✂️ Context limit reached. Stopped at {len(allowed_docs)} docs.")
            break
    
    # Graph ALWAYS gets added at the top (priority data)
    graph_text = graph_docs[0] if graph_docs else ""
    context_text = f"{graph_text}\n\n{chr(10).join(allowed_docs)}" if allowed_docs else "No relevant context."

    # --- 3. FEEDBACK INJECTION (For Loops) ---
    feedback_instruction = ""
    if feedback:
        print(f"   ⚠️ RETRYING WITH FEEDBACK: {feedback}")
        feedback_instruction = f"""
        PREVIOUS ANSWER WAS REJECTED.
        ERROR: {feedback}
        INSTRUCTION: Fix the error described above. Do NOT apologize.
        """

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
    - Be concise - no unnecessary preamble

    DO NOT:
    - Apologize or explain your reasoning process
    - Guess numbers not in the text
    - Ignore the verified calculation results
    """
    
    {feedback_instruction}

    user_prompt = f"""
    --- PREVIOUS CONVERSATION ---
    {history_text}
    
    --- CONTEXT ---
    {context_text}

    {math_context}
    
    --- QUESTION ---
    {question}
    """
    
    # Generate
    response = llm.generate(prompt=user_prompt, system_prompt=system_prompt)
    
    return {"generation": response, "retry_count": state.get("retry_count", 0) + 1}

def detect_fabricated_explanations(answer: str, context: str) -> dict:
    """
    Detect if answer fabricates explanations for contradictions.
    """
    violations = []
    
    # Check for invented causal links
    causal_phrases = [
        "due to", "because of", "as a result of", "caused by",
        "owing to", "on account of", "thanks to", "attributable to"
    ]
    
    for phrase in causal_phrases:
        if phrase in answer.lower() and phrase not in context.lower():
            violations.append(f"Fabricated causal link: '{phrase}' not in source")
    
    # Check for invented arithmetic
    answer_calcs = re.findall(r'(\d+)\s*[-+*/×÷]\s*(\d+)\s*=\s*(\d+)', answer)
    
    for calc_tuple in answer_calcs:
        calc_variations = [
            f"{calc_tuple[0]}-{calc_tuple[1]}={calc_tuple[2]}",
            f"{calc_tuple[0]} - {calc_tuple[1]} = {calc_tuple[2]}",
        ]
        
        found_in_source = any(var in context for var in calc_variations)
        
        if not found_in_source:
            violations.append(f"Invented calculation: '{calc_tuple[0]}-{calc_tuple[1]}={calc_tuple[2]}' not shown in source")
    
    return {
        "fabricated_explanations": len([v for v in violations if "causal" in v]) > 0,
        "invented_calculations": len([v for v in violations if "calculation" in v]) > 0,
        "violations": violations
    }


def check_source_explains_contradiction(context: str) -> bool:
    """
    Check if the source document actually explains contradictions/discrepancies.
    """
    explanation_markers = [
        "revised to", "corrected to", "restated as", "superseded by",
        "amended to", "updated to", "replaced with", "should be",
        "actually is", "the correct value is", "error was", "mistake was"
    ]
    
    context_lower = context.lower()
    return any(marker in context_lower for marker in explanation_markers)


def audit_node(state: AgentState):
    """
    FIXED: Enhanced Auditor with fabrication detection and ambiguity preservation.
    """
    print("--- 🕵️ AUDITING ANSWER ---")
    question = state["question"]
    answer = state["generation"]

    if "I don't know" in answer or "not found" in answer.lower():
        return {"audit_feedback": ""}

    context_snippet = "\n".join(state["documents"][:3]) if state["documents"] else "No context"

    # --- 1. FABRICATION DETECTION (NEW) ---
    print("   🔍 Checking for fabricated explanations...")
    fabrication_check = detect_fabricated_explanations(answer, context_snippet)

    if fabrication_check['violations']:
        print(f"   ❌ FABRICATION DETECTED: {fabrication_check['violations']}")
        violation_msg = "; ".join(fabrication_check['violations'][:2])
        return {
            "audit_feedback": f"FABRICATION ERROR: {violation_msg}. " +
                            "Only use explanations and calculations that explicitly appear in the source text. " +
                            "If source doesn't explain a discrepancy, state 'The document provides no explanation.'"
        }

    # --- 2. CONSTRAINT CHECKING ---
    print("   🔍 Extracting logic constraints...")
    predicates = constraint_checker.extract_predicates(question, context_snippet)

    if predicates:
        # Check consistency (Is the question itself contradictory?)
        is_consistent, explanation = constraint_checker.check_consistency(predicates, context_snippet)

        if not is_consistent:
            print(f"   ❌ INCONSISTENT: {explanation}")
            
            # FIXED: Check if SOURCE explains the contradiction
            source_explains = check_source_explains_contradiction(context_snippet)
            
            if source_explains:
                return {
                    "audit_feedback": f"CONTRADICTION DETECTED: {explanation}. " +
                                    "The source provides an explanation - use the source's resolution."
                }
            else:
                return {
                    "audit_feedback": f"UNRESOLVED CONTRADICTION: {explanation}. " +
                                    "The source does not explain this discrepancy. " +
                                    "State this explicitly - DO NOT INVENT an explanation."
                }

        # Validate answer
        is_valid, violation = constraint_checker.validate_answer_against_constraints(answer, predicates)

        if not is_valid:
            print(f"   ❌ INVALID ANSWER: {violation}")
            return {"audit_feedback": f"Answer violates logic constraint: {violation}"}

    # --- 3. STANDARD HALLUCINATION AUDIT ---
    auditor_system_prompt = f"""
    You are a Strict Quality Control Auditor. 
    Check the 'Answer' against the 'Context'.
    
    PASS CRITERIA:
    1. Does the answer hallucinate numbers not in the text?
    2. Does the answer mix up dates (e.g., Q1 vs Q2)?
    3. Does the answer fabricate explanations using phrases like "due to" or "because" 
       that don't appear in the context?
    4. Does the answer invent arithmetic calculations not shown in the text?
    
    If PASS: Return exactly "PASS".
    If FAIL: Return a concise description of the error.
    """

    user_prompt = f"""
    --- CONTEXT SNIPPET ---
    {context_snippet[:2000]} 
    
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

# --- CONDITIONAL EDGES ---

def decide_next_step(state: AgentState):
    """
    Determines if we should retry (Feedback Loop) or End.
    """
    feedback = state.get("audit_feedback", "")
    retries = state.get("retry_count", 0)

    if feedback and retries < 2: # Limit retries to 2 to prevent loops
        return "retry"
    
    return "end"

# --- GRAPH BUILDER ---

workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("decompose", decompose_query_node)  # <--- NEW
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("generate", generate_node)
workflow.add_node("audit", audit_node)

# Add Edges
workflow.set_entry_point("decompose")  # <--- Start with decomposition
workflow.add_edge("decompose", "retrieve")  # Then retrieve
workflow.add_edge("retrieve", "generate")
workflow.add_edge("generate", "audit")

# Conditional Edge: Audit -> (Generate OR End)
workflow.add_conditional_edges(
    "audit",
    decide_next_step,
    {
        "retry": "generate",
        "end": END
    }
)

# Compile
app_graph = workflow.compile()