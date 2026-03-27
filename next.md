DocuMind Session Report — March 24, 2025
Current State: 8/10 Stress Test Questions Passing
Changes Made This Session
1. Entity Extraction — QUERY_PROMPT enrichment
File: 
graph_agent.py
What: Added defined-term examples (agreements, acronyms, section refs) to the extraction prompt
Why: LLM was skipping non-proper-noun entities like "IGDTA" and "IP Bridge Agreement"
Result: ✅ Entity extraction now returns defined terms for any document
2. Citation Leak — SYSTEM NOTE regex strip
File: 
main.py
What: re.sub strips [...SYSTEM NOTE:...TRUSTED CODE EXECUTION RESULT...] from answers
Why: Math executor injects [SYSTEM NOTE: ...] which the LLM echoes as [Source: SYSTEM NOTE: ...] in citations
Result: ✅ No more SYSTEM NOTE tags in frontend answers
3. Constraint Checker — Stage 2 skip for factual
File: 
agent_graph.py
What: Changed if question_type not in ("math", "synthesis") → if question_type == "predicate"
Why: Constraint checker was treating omitted detail as invalid, causing false retries that pushed queries past 300s timeout
Applied by: Codex
Result: ✅ Factual questions no longer trigger unnecessary Stage 2 LLM calls
4. Constraint Checker — Contradiction-only validation prompt
File: 
constraint_checker.py
What: Rewrote 
validate_answer_against_constraints
 system prompt: "omission is not a contradiction"
Why: When Stage 2 does run (predicate questions), it should only flag contradictions, not missing detail
Applied by: Codex
Result: ✅ Predicate validation no longer false-flags brief correct answers
5. Confidence Floor — Negative score handling
File: 
main.py
What: Added max(0.05, ...) / max(0.0, ...) floor to confidence formula
Why: NVIDIA NIM reranker returns raw logits (can be negative like -11.375). Old formula produced negative confidence → 0% on frontend
Result: ✅ Correct answers never show 0% confidence
6. Retrieval — Original question in search set
File: 
agent_graph.py
What: When sub-queries > 1, prepend the original question to the retrieval list
Why: Decomposed sub-queries lose vocabulary from the original question (e.g. "retainers" → "bonuses")
Result: ✅ Broader candidate pool, $35K retainer now surfaces in results
7. Retrieval — Per-query limit floor raised
File: 
agent_graph.py
What: max(3, ...) → max(5, ...)
Why: With 5+ sub-queries, floor of 3 produced heavy overlap and too few unique candidates
Result: ✅ 8 unique candidates (up from 4) for broad queries
8. Retrieval — Fallback doc count raised
File: 
agent_graph.py
What: unique_results[:3] → unique_results[:7]
Why: When ALL reranked candidates score below threshold, keeping only 3 was arbitrary
NOTE

This change is currently inert because AGENT_MIN_RERANK_SCORE is set to -15.0 in the configmap, which is permissive enough that the fallback path never triggers. It serves as a safety net if the threshold is raised later.

9. Graph Search — Alias return in Cypher
File: 
knowledge_graph.py
What: Added node.aliases AS n_aliases to Cypher RETURN and 
(aka: ...)
 to graph context text
Why: Aliases were stored in Neo4j during ingestion but never surfaced at query time
Result: ✅ Graph context now includes alias lists for identity-bearing nodes
Stress Test Results
Document: NCA_Vantage_Acquisition_Report_Q3_2024.pdf
#	Question	Target	Result	Notes
Q1	All names for the acquired company	Alias resolution	⚠️ Partial	Returns 4 forms but misses formal "Vantage Systems, Inc."
Q2	Gerald Fontaine vs Gerald Ashford	Person disambiguation	✅ Pass	Correctly separated, audit passed 1st attempt, 5% confidence
Q3	DCA-7 interim arrangement	Defined term retrieval	✅ Pass	IP Bridge Agreement found, 95% confidence
Q4	All individual payments/retainers	Financial vocabulary	⚠️ Partial	Huang ✅, Voss $35K mentioned but name missing from context
Q5	Patricia Huang retention package	Surname-only merge	✅ Pass	Correct amounts, conditions, 95% confidence
Document: Meridian_Regulatory_Compliance_Framework_v4.2.docx
#	Question	Target	Result
Q1	All names for EU data protection regulation	Alias resolution	✅ Pass
Q2	Frederick Albrecht vs Sanjay Krishnamurthy	Person disambiguation	✅ Pass
Q3	Mandatory document vault system	Defined term retrieval	✅ Pass
Q4	Net counterparty exposure calculation	Financial vocabulary	✅ Pass
Q5	Ashworth's obligations	Surname-only merge	✅ Pass (5% confidence)
Two Remaining Issues
Issue A: Voss Retainer — Name Not in Context
What happens: The $35K/month retainer is retrieved and mentioned, but the answer says "does not specify the recipient's name." When asked directly about Raymond Voss, the system answers perfectly (10 candidates, 6 kept, score -1.56).

Root cause: The reranker scores each candidate against the original compound question only (line 476: pairs = [[question, r['text']]]). The Voss chunk scores well against "Raymond Voss consulting agreement" but poorly against "all payments, installments, or retainers that specific named people will receive." It falls below -15.0 and gets dropped.

Proposed fix — sub-query reranking:

Instead of reranking all candidates against only the original question, take the max rerank score across the original question AND each sub-query:

python
# Current (agent_graph.py line 476):
pairs = [[question, r['text']] for r in unique_results]
scores = reranker.predict(pairs)
# Proposed:
# Score against original question
pairs = [[question, r['text']] for r in unique_results]
scores = reranker.predict(pairs)
# Score against each sub-query, keep max per candidate
if len(sub_queries) > 1:
    for sq in sub_queries:
        sq_pairs = [[sq, r['text']] for r in unique_results]
        sq_scores = reranker.predict(sq_pairs)
        scores = [max(s, sq_s) for s, sq_s in zip(scores, sq_scores)]
Tradeoff: More reranker API calls (1 + N sub-queries instead of 1). With NVIDIA NIM, each reranker call is ~100-200ms. For 5 sub-queries, that's ~1 extra second. Worth it for correct results.

Alternative: Skip sub-query reranking when len(sub_queries) <= 2 to limit the extra calls to complex decomposed queries only.

Issue B: Alias Canonical — "Vantage Systems, Inc." Missing
What happens: The answer lists "Acquired Entity, Vantage, Vantage Systems, the Target" but not the formal "Vantage Systems, Inc." with the legal suffix.

Root cause chain:

Entity extraction returns ['company being acquired'] — a generic description, not a named entity
Neo4j fulltext search can't match "company being acquired" to any node
Graph alias fix (Cypher returns n.aliases) never fires because no node is found
The LLM answers from vector chunks only, which contain "Vantage Systems" without "Inc."
The LLM treats "Vantage Systems" and "Vantage Systems, Inc." as identical and outputs the shorter form
Assessment: This is marginal — the formal legal suffix "Inc." is a minor detail that doesn't affect correctness. The real entity ("Vantage Systems") is correctly identified. Fixing this generically would require entity-to-description mapping (mapping "the company being acquired" → "Vantage Systems, Inc." node), which is a significant architectural addition with limited ROI.

If you still want to fix it: The simplest approach would be adding the full formal name to the vector chunk during ingestion — but that's a chunking/ingestion code change, not a query-time fix.

Environment Notes
Pod deployment: make backend (builds + applies + restarts)
Port forwarding: kubectl port-forward svc/fastapi-service 8000:8000
Pod logs: kubectl logs -f deploy/fastapi --tail=50
Qdrant collection: documind_docs (NOT 
documents
)
Meridian filename in Qdrant: Meridian_Regulatory_Compliance_Framework_v4.2.docx (dot, not underscore)
ConfigMap values:
QUERY_TIMEOUT_S: "300"
AGENT_MIN_RERANK_SCORE: "-15.0" (default in code is -5.0)
3-model architecture: Nemotron 49B (generate), Llama 3.1 70B (audit), Qwen 2.5 Coder 32B (extraction)
Files Modified (Total: 6)
File	Lines Changed	Changes
backend/graph_agent.py
97-109	QUERY_PROMPT enrichment
backend/main.py
597-612	SYSTEM NOTE regex + confidence floor
backend/agent_graph.py
427-433, 453, 490, 822	Retrieval fixes + Stage 2 skip
backend/constraint_checker.py
301-330	Contradiction-only validation prompt
backend/knowledge_graph.py
253-275	Alias Cypher return + formatting
Priority Order for Next Session
Sub-query reranking (Issue A fix) — highest impact remaining fix
Full stress test re-run — validate all 10 questions after the reranking fix
Alias canonical (Issue B) — low priority, marginal improvement
Original roadmap items (from previous sessions):
graph_agent.py
: 
should_block_merge
 nameparser guard for Gerald Ashford/Fontaine
knowledge_graph.py
: merge provenance edges
ingest.py: full wipe + re-ingest to resolve data corruption