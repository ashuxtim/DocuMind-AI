"""
Constraint Satisfaction Layer for DocuMind
Prevents logical contradictions in answers.
"""
import hashlib
import json
import re
from typing import List, Tuple, Dict

import networkx as nx

# ---------------------------------------------------------------------------
# Fix 6 — Module-level predicate extraction cache
# Key: md5(question + context[:1000])
# Value: JSON-serialised list of predicates
#
# ⚠️  NOT thread-safe for Celery concurrency > 1.
#     If concurrency increases beyond solo, upgrade to threading.Lock or
#     replace with a module-level lru_cache on a plain function.
# ---------------------------------------------------------------------------
_PREDICATE_CACHE: Dict[str, str] = {}


class ConstraintChecker:
    def __init__(self, llm):
        self.llm = llm

    # -----------------------------------------------------------------------
    # Fix 1 — Robust JSON parsing helpers
    # Copied verbatim from graph_agent.py — do not diverge.
    # -----------------------------------------------------------------------
    def _parse_json_list(self, response: str) -> list:
        """Robustly extract a JSON array from any LLM response."""
        clean = re.sub(r'```(?:json)?', '', response).strip()
        match = re.search(r'\[.*\]', clean, re.DOTALL)
        if not match:
            return []
        try:
            result = json.loads(match.group())
            return result if isinstance(result, list) else []
        except json.JSONDecodeError:
            return []

    def _parse_json_dict(self, response: str) -> dict:
        """Robustly extract a JSON object from any LLM response."""
        clean = re.sub(r'```(?:json)?', '', response).strip()
        match = re.search(r'\{.*\}', clean, re.DOTALL)
        if not match:
            return {}
        try:
            result = json.loads(match.group())
            return result if isinstance(result, dict) else {}
        except json.JSONDecodeError:
            return {}

    # -----------------------------------------------------------------------
    # extract_predicates
    # Fix 1 — uses _parse_json_list
    # Fix 5 — context window raised to 2000 chars
    # Fix 6 — result cached by md5(question + context[:1000])
    # -----------------------------------------------------------------------
    def extract_predicates(self, question: str, context: str) -> List[str]:
        """
        Extract logical constraints from question and context.
        Returns list of predicate strings.

        Context is truncated to 2000 chars for the LLM call.
        Results are cached by question + context hash to avoid repeated
        Groq calls in the audit retry loop.
        """
        # Fix 6 — cache check before any LLM call
        raw = f"{question.strip().lower()}::{context[:1000]}"
        cache_key = hashlib.md5(raw.encode()).hexdigest()
        if cache_key in _PREDICATE_CACHE:
            return json.loads(_PREDICATE_CACHE[cache_key])

        result = self._do_extract_predicates(question, context)

        # Fix 6 — store result
        _PREDICATE_CACHE[cache_key] = json.dumps(result)
        return result

    def _do_extract_predicates(self, question: str, context: str) -> List[str]:
        """Actual LLM call for predicate extraction. Called only on cache miss."""
        system_prompt = """You are a logic extraction expert.
        Extract formal constraints from the question and context.

        CRITICAL: Preserve all numeric values exactly as written.
        Do not convert, scale, abbreviate, or reformat any numbers.
        $9,720,000 must remain $9,720,000 — never $9.72M or $9,720,000,000.

        Output JSON array of constraint strings.
        Example:
        Question: "Are there records with zero transactions where all records must have ratio >= 20?"
        Output: [
            "exists(record) where transactions(record) == 0",
            "forall(record) ratio(record) >= 20",
            "ratio = transactions / records"
        ]
        """

        # Fix 5 — raised from 500 to 2000 chars
        prompt = f"""Extract constraints:

        Question: {question}

        Context:
        {context[:2000]}

        JSON array:"""

        try:
            response = self.llm.generate(prompt, system_prompt)
            return self._parse_json_list(response)  # Fix 1
        except Exception as e:
            print(f"   ⚠️ Predicate extraction failed: {e}")
            return []

    # -----------------------------------------------------------------------
    # check_consistency
    # Fix 3 — len(predicates) > 1 gate removed; LLM check always runs
    # -----------------------------------------------------------------------
    def check_consistency(self, predicates: List[str], context: str) -> Tuple[bool, str]:
        """
        Check if predicates are mutually consistent.
        Returns (is_consistent, explanation).
        """
        if not predicates:
            return True, "No constraints to check"

        # Rule 1: Detect zero vs non-zero contradictions (fast heuristic)
        has_zero    = any(re.search(r'==\s*0|zero', p.lower()) for p in predicates)
        has_greater = any(re.search(r'>=\s*[1-9]|>\s*0', p) for p in predicates)
        has_all     = any(re.search(r'forall|all|every', p.lower()) for p in predicates)

        if has_zero and has_greater and has_all:
            return False, "CONTRADICTION: Cannot have ∃(zero) AND ∀(>0) simultaneously"

        # Rule 2: Detect circular dependency (Fix 4 — networkx)
        if self._detect_circular_dependency(predicates):
            return False, "CIRCULAR DEPENDENCY: Definition depends on itself"

        # Rule 3: LLM check — Fix 3: always runs, gate removed
        return self._llm_consistency_check(predicates, context)

    # -----------------------------------------------------------------------
    # Fix 4 — Circular dependency detection via networkx
    # Replaces hand-rolled DFS which had documented rec_stack fragility.
    # Only definition-style predicates (X = ...) are added to the graph.
    # Quantifier predicates (forall, exists, all(), any()) are skipped.
    # -----------------------------------------------------------------------
    def _detect_circular_dependency(self, predicates: List[str]) -> bool:
        """
        Detect circular definitions using networkx DiGraph.
        Returns True if a cycle exists in definition dependencies.
        """
        G = nx.DiGraph()

        definition_pattern = re.compile(r'^(\w+)\s*=\s*(.+)$')
        skip_keywords = {
            "if", "else", "and", "or", "not", "in",
            "True", "False", "None", "forall", "exists",
        }
        quantifier_prefixes = ("forall", "exists", "∀", "∃", "all(", "any(")

        for pred in predicates:
            pred_clean = pred.strip()
            # Skip quantifier predicates — they are not definitions
            if any(pred_clean.lower().startswith(q) for q in quantifier_prefixes):
                continue

            match = definition_pattern.match(pred_clean)
            if match:
                left = match.group(1)
                right_vars = re.findall(r'\b([a-zA-Z_]\w*)\b', match.group(2))
                deps = [v for v in right_vars
                        if v not in skip_keywords and v != left]
                for dep in deps:
                    G.add_edge(left, dep)  # left depends on dep

        return not nx.is_directed_acyclic_graph(G) if G.edges else False

    # -----------------------------------------------------------------------
    # _llm_consistency_check
    # Fix 1 — uses _parse_json_dict
    # Fix 5 — context window raised to 2000 chars (was 800)
    # -----------------------------------------------------------------------
    def _llm_consistency_check(self, predicates: List[str], context: str) -> Tuple[bool, str]:
        """Use LLM for complex consistency checking."""
        system_prompt = """You are a formal logic checker.
        Check if these predicates can ALL be true simultaneously.

        Return JSON:
        {"consistent": true/false, "explanation": "..."}
        """

        # Fix 5 — raised from 800 to 2000 chars to match extract_predicates
        prompt = f"""Check consistency:

        Predicates:
        {chr(10).join(f"{i+1}. {p}" for i, p in enumerate(predicates))}

        Context:
        {context[:2000]}

        JSON:"""

        try:
            response = self.llm.generate(prompt, system_prompt)
            result = self._parse_json_dict(response)  # Fix 1
            if result:
                return result['consistent'], result.get('explanation', 'LLM check')
            return True, "LLM check inconclusive"
        except Exception as e:
            print(f"   ⚠️ Consistency check failed: {e}")
            return True, "LLM check failed"

    # -----------------------------------------------------------------------
    # validate_answer_against_constraints
    # Fix 1 — uses _parse_json_dict
    # Fix 2 — bare except replaced; VALIDATION_ERROR prefix on message
    # -----------------------------------------------------------------------
    def validate_answer_against_constraints(
        self, answer: str, predicates: List[str]
    ) -> Tuple[bool, str]:
        """
        Check if the answer violates any constraints.

        On LLM failure returns (True, "VALIDATION_ERROR: ...") — the caller
        (audit_node in agent_graph.py) should check for this prefix and treat
        it as a warning rather than a confirmed pass.
        """
        if not predicates:
            return True, "No constraints to check"

        system_prompt = """Check if this answer violates the constraints.
        Return JSON:
        {"valid": true/false, "violation": "description or null"}
        """

        prompt = f"""Validate:

        Answer: {answer}

        Constraints:
        {chr(10).join(predicates)}

        JSON:"""

        try:
            response = self.llm.generate(prompt, system_prompt)
            result = self._parse_json_dict(response)  # Fix 1

            if result:
                valid     = result.get('valid', True)
                violation = result.get('violation') or ''
                if not valid:
                    return False, violation

            return True, "Answer consistent with constraints"

        except Exception as e:
            # Fix 2 — never silently pass; surface the error with a recognisable prefix
            # audit_node checks for "VALIDATION_ERROR:" and treats it as a warning, not a pass
            print(f"   ⚠️ Constraint validation error: {e}")
            return True, f"VALIDATION_ERROR: {str(e)[:100]}"
