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

    def _normalize_predicates(self, predicates: List[str]) -> List[str]:
        """
        Normalize time/duration expressions so equivalent values
        don't appear as contradictions to the LLM consistency checker.
        '2 years', 'two years', 'two-year', '24 months', 'twenty-four months',
        'twenty-four (24) months' all become '24_months'.
        """
        patterns = [
            (r'\btwo[\s-]year\w*\b',                        '24_months'),
            (r'\b2[\s-]year\w*\b',                          '24_months'),
            (r'\btwenty[\s-]four\s*\(?\s*24\s*\)?\s*month\w*\b', '24_months'),
            (r'\btwenty[\s-]four\s*month\w*\b',             '24_months'),
            (r'\b24[\s-]month\w*\b',                        '24_months'),
            (r'\bone[\s-]year\w*\b',                        '12_months'),
            (r'\b1[\s-]year\w*\b',                          '12_months'),
            (r'\btwelve\s*month\w*\b',                      '12_months'),
            (r'\b12[\s-]month\w*\b',                        '12_months'),
            (r'\bthree[\s-]year\w*\b',                      '36_months'),
            (r'\b3[\s-]year\w*\b',                          '36_months'),
            (r'\bthirty[\s-]six\s*month\w*\b',              '36_months'),
            (r'\b36[\s-]month\w*\b',                        '36_months'),
            (r'\bfive[\s-]year\w*\b',                       '60_months'),
            (r'\b5[\s-]year\w*\b',                          '60_months'),
        ]
        normalized = []
        for pred in predicates:
            p = pred
            for pattern, replacement in patterns:
                p = re.sub(pattern, replacement, p, flags=re.IGNORECASE)
            normalized.append(p)
        return normalized

    def _filter_reference_predicates(self, predicates: List[str]) -> List[str]:
        """
        Deterministically remove predicates that are document cross-references.
        These are never logical constraints — they cause false violations when
        the retrieved chunk label differs from the cross-reference in the text.
        """
        skip_patterns = [
            r'\bsection\s+\d',
            r'\bpage\s+\d',
            r'\bappendix\b',
            r'\bsee\s+(section|page|above|below)\b',
            r'summarized\s+in\s+section',
            r'described\s+in\s+section',
            r'outlined\s+in\s+section',
            r'refer\s+to\s+section',
        ]
        compiled = [re.compile(p, re.IGNORECASE) for p in skip_patterns]
        return [
            pred for pred in predicates
            if not any(pat.search(pred) for pat in compiled)
        ]

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
        result = self._filter_reference_predicates(result)

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

        EXCLUDE any predicate that references a section number, page number, or
        cross-reference to another part of the document (e.g. 'terms are summarized
        in Section 5.2'). Only extract predicates about facts, values, names, dates,
        or logical relationships between entities.

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
            response = self.llm.generate(prompt, system_prompt, max_tokens=400)
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

        # Rule 3: LLM check — normalize time expressions first, then check
        normalized = self._normalize_predicates(predicates)
        return self._llm_consistency_check(normalized, context)

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
        system_prompt = """You are a strict formal logic checker.
        Check if these predicates can ALL be true simultaneously.

        EQUIVALENCE RULES — these are NEVER contradictions:
        - Same quantity expressed differently: "$35,000/month" = "$35,000 per month" = "monthly retainer of $35,000"
        - Normalized time tokens are canonical: "24_months" always equals "24_months"
        - Active vs passive voice describing the same fact is NOT a contradiction
        - A fact mentioned in multiple predicates with slightly different wording is NOT a contradiction

        ONLY return consistent=false when there is a GENUINE logical impossibility:
        - Two different numeric values for the same quantity (e.g. $35,000 vs $40,000)
        - Mutually exclusive states (e.g. entity both exists and does not exist)
        - Mathematical impossibility (X > 0 AND X = 0)

        When in doubt, return consistent=true. False positives cause more harm than false negatives.

        Return JSON only:
        {"consistent": true/false, "explanation": "brief reason or null"}
        """

        # Fix 5 — raised from 800 to 2000 chars to match extract_predicates
        prompt = f"""Check consistency:

        Predicates:
        {chr(10).join(f"{i+1}. {p}" for i, p in enumerate(predicates))}

        Context:
        {context[:2000]}

        JSON:"""

        try:
            response = self.llm.generate(prompt, system_prompt, max_tokens=400)
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
        Check if the answer directly contradicts any constraints.

        This validator is for contradiction detection, not completeness scoring.
        A concise answer can be valid even if it omits related facts that appear
        in the retrieved context, as long as it does not state something false.

        On LLM failure returns (True, "VALIDATION_ERROR: ...") — the caller
        (audit_node in agent_graph.py) should check for this prefix and treat
        it as a warning rather than a confirmed pass.
        """
        if not predicates:
            return True, "No constraints to check"

        system_prompt = """You are a contradiction checker.
        Determine whether the answer DIRECTLY contradicts any constraint.

        Mark valid=false ONLY when the answer explicitly conflicts with a constraint,
        such as:
        - a different number, date, section, or named entity for the same fact
        - saying something is allowed when a constraint says it is prohibited
        - saying something does not exist when a constraint says it does exist

        DO NOT mark the answer invalid merely because it is brief, incomplete,
        or does not mention every constraint. Omission is not a contradiction.

        When in doubt, return valid=true.

        Return JSON only:
        {"valid": true/false, "violation": "brief contradiction or null"}
        """

        prompt = f"""Validate:

        Answer: {answer}

        Constraints:
        {chr(10).join(predicates)}

        JSON:"""

        try:
            response = self.llm.generate(prompt, system_prompt, max_tokens=400)
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
