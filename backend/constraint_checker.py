"""
Constraint Satisfaction Layer for DocuMind
Prevents logical contradictions in answers.
"""
import json
import re
from typing import List, Tuple, Dict

class ConstraintChecker:
    def __init__(self, llm):
        self.llm = llm

    def extract_predicates(self, question: str, context: str) -> List[str]:
        """
        Extract logical constraints from question and context.
        Returns list of predicate strings.
        """
        system_prompt = """You are a logic extraction expert.
        Extract formal constraints from the question and context.

        Output JSON array of constraint strings.
        Example:
        Question: "Are there records with zero transactions where all records must have ratio >= 20?"
        Output: [
            "exists(record) where transactions(record) == 0",
            "forall(record) ratio(record) >= 20",
            "ratio = transactions / records"
        ]
        """

        prompt = f"""Extract constraints:

        Question: {question}

        Context (first 500 chars):
        {context[:500]}

        JSON array:"""

        try:
            response = self.llm.generate(prompt, system_prompt)

            clean = response.replace("```json", "").replace("```", "").strip()
            start = clean.find('[')
            end = clean.rfind(']') + 1

            if start != -1 and end > start:
                return json.loads(clean[start:end])

            return []
        except Exception as e:
            print(f"   ⚠️ Predicate extraction failed: {e}")
            return []

    def check_consistency(self, predicates: List[str], context: str) -> Tuple[bool, str]:
        """
        Check if predicates are mutually consistent.
        Returns (is_consistent, explanation)
        """
        if not predicates:
            return True, "No constraints to check"

        # Rule 1: Detect zero vs non-zero contradictions (Hard-coded heuristics)
        has_zero = any(re.search(r'==\s*0|zero', p.lower()) for p in predicates)
        has_greater = any(re.search(r'>=\s*[1-9]|>\s*0', p) for p in predicates)
        has_all = any(re.search(r'forall|all|every', p.lower()) for p in predicates)

        if has_zero and has_greater and has_all:
            return False, "CONTRADICTION: Cannot have ∃(zero) AND ∀(>0) simultaneously"

        # Rule 2: Detect circular dependency
        has_circular = self._detect_circular_dependency(predicates)
        if has_circular:
            return False, "CIRCULAR DEPENDENCY: Definition depends on itself (e.g., Active Record defined by Ratio which depends on Active Records)"

        # Rule 3: Use LLM for complex checks
        if len(predicates) > 1:
            return self._llm_consistency_check(predicates, context)

        return True, "Constraints appear consistent"

    def _detect_circular_dependency(self, predicates: List[str]) -> bool:
        """Detect simple circular definitions"""
        # Build dependency graph
        dependencies = {}

        for pred in predicates:
            # Extract variables (very naive - assumes pattern "X = f(Y)")
            match = re.search(r'(\w+)\s*=.*?(\w+)', pred)
            if match:
                left, right = match.groups()
                if left not in dependencies:
                    dependencies[left] = []
                dependencies[left].append(right)

        # Check for cycles
        def has_cycle(node, visited, rec_stack):
            visited.add(node)
            rec_stack.add(node)

            for neighbor in dependencies.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor, visited, rec_stack):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        visited = set()
        for node in dependencies:
            if node not in visited:
                if has_cycle(node, visited, set()):
                    return True

        return False

    def _llm_consistency_check(self, predicates: List[str], context: str) -> Tuple[bool, str]:
        """Use LLM for complex consistency checking"""
        system_prompt = """You are a formal logic checker.
        Check if these predicates can ALL be true simultaneously.

        Return JSON:
        {"consistent": true/false, "explanation": "..."}
        """

        prompt = f"""Check consistency:

        Predicates:
        {chr(10).join(f"{i+1}. {p}" for i, p in enumerate(predicates))}

        Context:
        {context[:800]}

        JSON:"""

        try:
            response = self.llm.generate(prompt, system_prompt)

            clean = response.replace("```json", "").replace("```", "").strip()
            start = clean.find('{')
            end = clean.rfind('}') + 1

            if start != -1:
                result = json.loads(clean[start:end])
                return result['consistent'], result.get('explanation', 'LLM check')

            return True, "LLM check inconclusive"
        except:
            return True, "LLM check failed"

    def validate_answer_against_constraints(self, answer: str, predicates: List[str]) -> Tuple[bool, str]:
        """Check if the answer violates any constraints"""
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

            clean = response.replace("```json", "").replace("```", "").strip()
            start = clean.find('{')
            end = clean.rfind('}') + 1

            if start != -1:
                result = json.loads(clean[start:end])
                valid = result.get('valid', True)
                violation = result.get('violation', '')

                if not valid:
                    return False, violation

            return True, "Answer consistent with constraints"
        except:
            return True, "Validation inconclusive"