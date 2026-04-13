"""
Code Execution Layer for DocuMind
Prevents LLM arithmetic hallucinations by forcing Python code execution.
"""

import asyncio
import hashlib
import json
import os
import re
import resource
import subprocess
import tempfile
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Fix 8 — Module-level variable extraction cache
# Key: md5(context[:2000] + question)
# Value: JSON-serialised dict of extracted variables
#
# ⚠️  NOT thread-safe for Celery concurrency > 1.
#     If concurrency increases beyond solo, upgrade to threading.Lock or
#     replace with a module-level lru_cache on a plain function.
# ---------------------------------------------------------------------------
_VAR_CACHE: Dict[str, str] = {}

# ---------------------------------------------------------------------------
# Fix 7 — Subprocess resource limits
# Applied via preexec_fn on Linux. No-op on non-Linux (import guard below).
# ---------------------------------------------------------------------------
def _set_subprocess_limits():
    """
    Set OS-level resource limits on the sandboxed subprocess.
    256MB virtual memory cap prevents memory bombs.
    10s CPU time cap prevents infinite loops that slip past timeout.
    Called as preexec_fn — runs inside the child process before exec.
    """
    try:
        # 256MB virtual memory
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        # 10s CPU time
        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    except Exception:
        pass  # Non-Linux or insufficient permissions — degrade gracefully

# Isolated temp directory for sandbox files — configurable via K8s ConfigMap.
# os.makedirs is intentionally NOT called here — moved inside execute_code_safely
# so a permissions failure doesn't crash the module at import time.
_SANDBOX_TMP_DIR = os.getenv("MATH_SANDBOX_TMP_DIR", "/tmp/documind_sandbox")


class MathExecutor:
    """
    Detects mathematical operations and forces code-based computation.
    Prevents "213 - 27 = 213" type hallucinations.
    """

    def __init__(self, llm_provider):
        self.llm = llm_provider

        # Fix 4 — strong math keywords only; removed high-FP words
        # (compare, count, index, adjust removed from original list)
        self._strong_math_keywords = [
            "calculate", "compute", "sum", "subtract", "add", "divide",
            "multiply", "ratio", "percentage", "total", "average", "mean",
            "difference", "reconcile", "derive", "net",
        ]

        self.math_operators = ["+", "-", "×", "÷", "/", "*", "=", "≥", "≤", ">", "<"]

    # -----------------------------------------------------------------------
    # Fix 2 — Robust JSON parsing helpers
    # Copied verbatim from graph_agent.py / constraint_checker.py.
    # Do not diverge — these must stay identical across all three files.
    # -----------------------------------------------------------------------
    def _parse_json_dict(self, response: str) -> dict:
        """Robustly extract a JSON object from any LLM response."""
        clean = re.sub(r'```(?:json|python)?', '', response).strip()
        match = re.search(r'\{.*\}', clean, re.DOTALL)
        if not match:
            return {}
        try:
            result = json.loads(match.group())
            return result if isinstance(result, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _parse_json_list(self, response: str) -> list:
        """Robustly extract a JSON array from any LLM response."""
        clean = re.sub(r'```(?:json|python)?', '', response).strip()
        match = re.search(r'\[.*\]', clean, re.DOTALL)
        if not match:
            return []
        try:
            result = json.loads(match.group())
            return result if isinstance(result, list) else []
        except json.JSONDecodeError:
            return []

    # -----------------------------------------------------------------------
    # Fix 4 — Stricter needs_math()
    # Requires: (strong keyword AND ≥2 numbers in question) OR explicit operator.
    # Original: any keyword + any single number — too many false positives.
    # -----------------------------------------------------------------------
    def needs_math(self, question: str) -> bool:
        """Detect if question requires mathematical computation."""
        q_lower = question.lower()

        # Explicit math operators in question text
        has_operator = any(op in question for op in ["+", "-", "×", "÷", "/", "*"])

        # Two or more distinct numbers in the question
        numbers = re.findall(r'\b\d+\.?\d*\b', question)
        has_multiple_numbers = len(numbers) >= 2

        # Strong math intent only — high-FP words removed
        has_strong_keyword = any(kw in q_lower for kw in self._strong_math_keywords)

        # Gate: strong keyword + multiple numbers, OR an explicit operator
        return (has_strong_keyword and has_multiple_numbers) or has_operator

    # -----------------------------------------------------------------------
    # Fix 6 — Number-dense context pre-filter for variable extraction
    # Scores lines by financial density, pulls up to max_chars of high-value
    # content regardless of original position in the context.
    # -----------------------------------------------------------------------
    def _extract_number_dense_context(self, context: str, max_chars: int = 6000) -> str:
        """
        Filter out pure-narrative lines (no numbers and no table structure) and
        return the remaining lines in their original document order up to
        max_chars.

        Lines are kept if they have any numeric content (score > 0) OR contain
        table-structural characters (pipe '|' or separator patterns like '---').
        Original ordering is preserved so that table header rows stay adjacent
        to their data rows — critical for the extraction LLM to resolve which
        column each value belongs to.

        Used only by extract_variables_from_context — which needs column/row
        anchoring to build a correctly-labelled variable dict.
        """
        lines = context.split('\n')
        kept_lines = []
        total = 0
        for line in lines:
            numbers = re.findall(r'\d+\.?\d*', line)
            has_financial = bool(re.search(r'[\$€£%]|\d+[MBK]|\d+\.\d+', line))
            score = len(numbers) * 2 + (5 if has_financial else 0)
            is_table_structure = bool('|' in line or re.search(r'[-=]{3,}', line))

            if score == 0 and not is_table_structure:
                continue

            if total + len(line) > max_chars:
                break
            kept_lines.append(line)
            total += len(line)

        filtered = '\n'.join(kept_lines)
        # Fallback: if filter produces nothing, use raw truncation
        return filtered if filtered.strip() else context[:max_chars]

    # -----------------------------------------------------------------------
    # extract_variables_from_context
    # Fix 5 — source-prefixed variable names for conflicting evidence
    # Fix 6 — number-dense pre-filter at 6000 chars
    # Fix 8 — result cached by md5(context[:2000] + question)
    # -----------------------------------------------------------------------
    def extract_variables_from_context(self, context: str, question: str) -> Dict:
        """
        Extract numerical values from context as Python variables.

        Conflicting values from different sources are preserved with distinct
        prefixed names (e.g., doc_a_revenue_millions vs doc_b_revenue_millions).
        Results cached by context+question hash to avoid repeated Groq calls
        in the audit retry loop.
        """
        # Fix 8 — cache check
        raw_key = f"{context[:2000]}::{question.strip().lower()}"
        cache_key = hashlib.md5(raw_key.encode()).hexdigest()
        if cache_key in _VAR_CACHE:
            return json.loads(_VAR_CACHE[cache_key])

        result = self._do_extract_variables(context, question)

        # Fix 8 — store result
        _VAR_CACHE[cache_key] = json.dumps(result)
        return result

    def _do_extract_variables(self, context: str, question: str) -> Dict:
        """Actual LLM call for variable extraction — only runs on cache miss."""
        # Fix 6 — number-dense filter instead of flat truncation
        filtered_context = self._extract_number_dense_context(context, max_chars=6000)

        # Fix 5 — source-prefix instructions added to prompt
        extraction_prompt = f"""Extract ALL numerical data from this text as Python variables.

Question: {question}

Text:
{filtered_context}

Instructions:
1. Find every number mentioned
2. Create descriptive variable names (snake_case)
3. Include units in names (e.g., revenue_millions, count_records)
4. Convert to int/float
5. If calculations shown (e.g., "214 - 37"), extract INTERMEDIATE values too
6. If multiple sources present, prefix variable names with source
   (e.g., doc_a_revenue_millions, doc_b_revenue_millions)
7. If same metric appears with DIFFERENT values, extract BOTH with distinct names
   — never produce duplicate keys
8. If a revision or restatement exists, extract BOTH original and restated values
   (e.g., original_revenue_millions and restated_revenue_millions)
9. Return ONLY a valid Python dict — no duplicate keys
10. TABLES — for any value extracted from a table with multiple columns:
    - The variable name MUST encode BOTH the row label AND the column header
    - Format: {{row_label}}_{{column_header}} in snake_case
    - If the column header is a time period (Q1 2023, Q2 2024, FY2022, etc.),
      always include it in the variable name
    - NEVER create a bare metric name like `total_headcount` when multiple
      time-period columns exist — each column value gets its own variable
    - Example: a table row "TOTAL HEADCOUNT | 310 | 401" under columns
      "Q1 2023 | Q2 2024" produces total_headcount_q1_2023 = 310 and
      total_headcount_q2_2024 = 401, NOT total_headcount = 310

Example 1 — conflicting sources:
Text: "Doc A: Revenue Q1 $50M. Doc B (Restated): Revenue Q1 $45M"
Output: {{"doc_a_q1_revenue_millions": 50, "doc_b_q1_revenue_millions_restated": 45}}

Example 2 — table extraction:
Text:
  Department      | Q1 2023 | Q2 2024
  Engineering     |   162   |   214
  TOTAL HEADCOUNT |   310   |   401
WRONG: {{"engineering_headcount": 162, "total_headcount": 310}}
CORRECT: {{"engineering_q1_2023": 162, "engineering_q2_2024": 214, "total_headcount_q1_2023": 310, "total_headcount_q2_2024": 401}}

Python dict:"""

        try:
            response = self.llm.generate(
                extraction_prompt,
                system_prompt="You are a data extractor. Output ONLY a Python dict."
            )
            return self._parse_json_dict(response)  # Fix 2
        except Exception as e:
            print(f"   ⚠️ Variable extraction error: {e}")
            return {}

    # -----------------------------------------------------------------------
    # generate_calculation_code
    # Fix 5 — code generation prompt instructs use of restated values
    # Fix 6 — flat context[:6000] (sequential narrative preserved)
    # -----------------------------------------------------------------------
    def generate_calculation_code(self, question: str, variables: Dict, context: str) -> str:
        """Generate Python code to answer the question."""
        vars_str = json.dumps(variables, indent=2)

        code_prompt = f"""Write Python code to answer this question using provided variables.

Question: {question}

Variables available:
{vars_str}

Context (for reference):
{context[:6000]}

Requirements:
1. Variables are already defined — DO NOT redefine them
2. Show step-by-step calculation with comments
3. Use intermediate variables
4. Store final answer in: result
5. Print result with label
6. If both original and restated values exist, use the RESTATED value in calculations
7. If a discrepancy exists between two source values, print BOTH with source labels
8. Output ONLY executable Python code

Code:"""

        try:
            response = self.llm.generate(
                code_prompt,
                system_prompt="You are a Python code generator. Output ONLY valid Python code."
            )

            code = response.replace("```python", "").replace("```", "").strip()

            # Prepend variable definitions
            var_defs = "\n".join([f"{k} = {v}" for k, v in variables.items()])

            return f"""# Extracted Variables
{var_defs}

# Calculation
{code}
"""
        except Exception as e:
            print(f"   ⚠️ Code generation error: {e}")
            return ""

    # -----------------------------------------------------------------------
    # execute_code_safely
    # Fix 1 — finally block guarantees temp file cleanup on all paths
    # Fix 7 — subprocess resource limits via preexec_fn
    # -----------------------------------------------------------------------
    def execute_code_safely(self, code: str, timeout: int = 10) -> Dict:
        """Execute Python code in subprocess sandbox with resource limits."""
        # Ensure sandbox directory exists — done here not at module level so a
        # permissions failure doesn't crash the module on import.
        # Falls back to /tmp if the configured path can't be created.
        sandbox_dir = _SANDBOX_TMP_DIR
        try:
            os.makedirs(sandbox_dir, exist_ok=True)
        except Exception:
            sandbox_dir = "/tmp"

        # Fix 1 — initialise before try so finally never hits NameError
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.py',
                prefix='math_exec_',
                dir=sandbox_dir,
                delete=False,
            ) as f:
                f.write(code)
                temp_file = f.name

            # Fix 7 — resource limits applied inside child process
            result = subprocess.run(
                ["python3", temp_file],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=sandbox_dir,
                preexec_fn=_set_subprocess_limits,
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "output": result.stdout.strip(),
                    "error": None,
                }
            else:
                return {
                    "success": False,
                    "output": None,
                    "error": result.stderr,
                }

        except subprocess.TimeoutExpired:
            return {"success": False, "output": None, "error": "Timeout"}
        except Exception as e:
            return {"success": False, "output": None, "error": str(e)}
        finally:
            # Fix 1 — guaranteed cleanup regardless of which path we took
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except Exception:
                    pass

    # -----------------------------------------------------------------------
    # validate_result
    # Fix 2 — _parse_json_dict replaces rfind block
    # Fix 2 — bare except replaced with except Exception as e + logging
    # -----------------------------------------------------------------------
    def validate_result(self, question: str, code: str, result: str, variables: Dict) -> Dict:
        """Sanity check the calculation result."""
        validation_prompt = f"""Verify the ARITHMETIC in this code is correct.

YOUR ROLE: You are a pure arithmetic checker. You verify that the code
correctly implements the requested math operations given the variables it
was provided. You do NOT have access to the source document and CANNOT
judge whether the variable values themselves are correct.

Do NOT assess whether the variable values are correct or match the source
document — only assess whether the code correctly uses the variables it
was given.

Question: {question}
Variables: {json.dumps(variables)}
Code: {code}
Result: {result}

Check:
1. Is the arithmetic correct? (Do the math operations in the code produce
   the printed result given the variable values?)
2. Does the code correctly implement what the question asks arithmetically?
   (e.g., if the question asks for a sum, does the code sum the right variables?
   If it asks for a ratio, does it divide the right ones?)
3. Is the result just copying an input value without performing any computation
   (input-echo hallucination)?
4. Are there variables that look suspicious — e.g., same metric name with
   different time periods where the wrong period may have been selected?
   If so, add a warning but do NOT set is_valid to false for this reason alone.

Return JSON:
{{"is_valid": true/false, "confidence": 0.0-1.0, "issues": [], "warnings": [], "explanation": "..."}}

IMPORTANT: Set is_valid to false ONLY for checks 1-3. Check 4 produces
warnings only — never invalidate a result because a variable VALUE looks wrong.

JSON:"""

        try:
            response = self.llm.generate(validation_prompt)
            parsed = self._parse_json_dict(response)  # Fix 2
            if parsed:
                return parsed
            return {
                "is_valid": True, "confidence": 0.5,
                "issues": [], "explanation": "Parse inconclusive",
            }
        except Exception as e:
            # Fix 2 — never silently pass; log the failure
            print(f"   ⚠️ Validation error: {e}")
            return {
                "is_valid": True, "confidence": 0.5,
                "issues": [], "explanation": f"VALIDATION_ERROR: {str(e)[:100]}",
            }

    # -----------------------------------------------------------------------
    # process_math_question
    # Fix 3 — validation re-enabled; step labels corrected to 1/4–4/4
    # -----------------------------------------------------------------------
    def process_math_question(self, question: str, context: str) -> Optional[Dict]:
        """
        Full pipeline: Extract → Code → Execute → Validate

        Returns None on any failure — caller falls back to plain LLM generation.
        """
        print("\n" + "=" * 80)
        print("🧮 MATH EXECUTION MODE ACTIVATED")
        print("=" * 80)

        # Step 1: Extract variables
        print("📊 Step 1/4: Extracting variables...")
        variables = self.extract_variables_from_context(context, question)
        if not variables:
            print("   ⚠️ No variables found — fallback to LLM")
            return None
        print(f"   ✅ Extracted {len(variables)} variables")

        # Step 2: Generate code
        print("\n💻 Step 2/4: Generating Python code...")
        code = self.generate_calculation_code(question, variables, context)
        if not code:
            print("   ⚠️ Code generation failed")
            return None

        # Step 3: Execute
        print("\n⚡ Step 3/4: Executing in sandbox...")
        exec_result = self.execute_code_safely(code)
        if not exec_result["success"]:
            print(f"   ❌ Execution failed: {exec_result['error']}")
            return None

        result_output = exec_result["output"]
        print(f"   ✅ Result: {result_output}")

        # Step 4: Validate — DO NOT SKIP
        # Catches input-echo hallucinations where LLM echoes an input variable
        # instead of computing the answer. Costs 1 Groq call, worth it.
        print("\n🔍 Step 4/4: Validating result...")
        validation = self.validate_result(question, code, result_output, variables)
        if not validation.get("is_valid", True):
            issues = "; ".join(validation.get("issues", []))
            print(f"   ❌ Validation FAILED: {issues}")
            return None

        confidence = validation.get("confidence", 0.8)
        print(f"   ✅ Validated (confidence: {confidence:.2f})")

        return {
            "success": True,
            "answer": result_output,
            "output": result_output,
            "confidence": confidence,
        }

    # -----------------------------------------------------------------------
    # Fix 9 — Async wrapper
    # One-line wrapper for future ainvoke migration.
    # Use this when calling from async LangGraph nodes directly.
    # -----------------------------------------------------------------------
    async def process_math_question_async(
        self, question: str, context: str
    ) -> Optional[Dict]:
        """Async wrapper — delegates to sync pipeline via asyncio.to_thread."""
        return await asyncio.to_thread(self.process_math_question, question, context)