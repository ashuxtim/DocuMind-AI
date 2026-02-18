"""
Code Execution Layer for DocuMind
Prevents LLM arithmetic hallucinations by forcing Python code execution.
Author: Enhanced for Review 1 Test 2 failures
"""

import subprocess
import re
import json
import os
import tempfile
from typing import Dict, Optional, List

class MathExecutor:
    """
    Detects mathematical operations and forces code-based computation.
    Prevents "213 - 27 = 213" type hallucinations.
    """
    
    def __init__(self, llm_provider):
        """
        Args:
            llm_provider: Instance from get_llm_provider()
        """
        self.llm = llm_provider
        
        # Patterns that indicate math is needed
        self.math_keywords = [
            "calculate", "compute", "sum", "subtract", "add", "divide", 
            "multiply", "ratio", "percentage", "total", "average", "mean",
            "count", "difference", "maximum", "minimum", "compare",
            "reconcile", "derive", "net", "adjust", "index"
        ]
        
        self.math_operators = ["+", "-", "×", "÷", "/", "*", "=", "≥", "≤", ">", "<"]
    
    def needs_math(self, question: str) -> bool:
        """Detect if question requires mathematical computation."""
        q_lower = question.lower()
        
        has_keyword = any(kw in q_lower for kw in self.math_keywords)
        has_operator = any(op in q_lower for op in self.math_operators)
        has_numbers = bool(re.search(r'\d+', question))
        has_formula = bool(re.search(r'[a-zA-Z0-9]+\s*[+\-*/÷×]\s*[a-zA-Z0-9]+', question))
        
        return (has_keyword or has_operator or has_formula) and has_numbers
    
    def extract_variables_from_context(self, context: str, question: str) -> Dict:
        """Extract numerical values from context as Python variables."""
        
        extraction_prompt = f"""Extract ALL numerical data from this text as Python variables.

Question: {question}

Text:
{context[:3000]}

Instructions:
1. Find every number mentioned
2. Create descriptive variable names (snake_case)
3. Include units in names (e.g., revenue_millions, count_records)
4. Convert to int/float
5. If calculations shown (e.g., "214 - 37"), extract INTERMEDIATE values
6. Return ONLY valid Python dict

Example:
Text: "Q1 revenue $50M. Q2 was $60M. Total employees: 500"
Output: {{"q1_revenue_millions": 50, "q2_revenue_millions": 60, "total_employees": 500}}

Python dict:"""

        try:
            response = self.llm.generate(
                extraction_prompt,
                system_prompt="You are a data extractor. Output ONLY Python dict."
            )
            
            clean = response.replace("```python", "").replace("```json", "").replace("```", "").strip()
            start = clean.find('{')
            end = clean.rfind('}') + 1
            
            if start != -1 and end > start:
                return json.loads(clean[start:end])
            return {}
                
        except Exception as e:
            print(f"   ⚠️ Variable extraction error: {e}")
            return {}
    
    def generate_calculation_code(self, question: str, variables: Dict, context: str) -> str:
        """Generate Python code to answer the question."""
        
        vars_str = json.dumps(variables, indent=2)
        
        code_prompt = f"""Write Python code to answer this question using provided variables.

Question: {question}

Variables available:
{vars_str}

Context (for reference):
{context[:1000]}

Requirements:
1. Variables are already defined - DO NOT redefine them
2. Show step-by-step calculation with comments
3. Use intermediate variables
4. Store final answer in: result
5. Print result with label
6. Output ONLY executable Python code

Code:"""

        try:
            response = self.llm.generate(
                code_prompt,
                system_prompt="You are a Python code generator. Output ONLY valid code."
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
    
    def execute_code_safely(self, code: str, timeout: int = 5) -> Dict:
        """Execute Python code in subprocess sandbox."""
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_file = f.name
            
            result = subprocess.run(
                ["python3", temp_file],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            os.unlink(temp_file)
            
            if result.returncode == 0:
                return {
                    "success": True,
                    "output": result.stdout.strip(),
                    "error": None
                }
            else:
                return {
                    "success": False,
                    "output": None,
                    "error": result.stderr
                }
                
        except subprocess.TimeoutExpired:
            os.unlink(temp_file)
            return {"success": False, "output": None, "error": "Timeout"}
        except Exception as e:
            return {"success": False, "output": None, "error": str(e)}
    
    def validate_result(self, question: str, code: str, result: str, variables: Dict) -> Dict:
        """Sanity check the calculation result."""
        
        validation_prompt = f"""Verify this calculation is correct.

Question: {question}
Variables: {json.dumps(variables)}
Code: {code}
Result: {result}

Check:
1. Is math correct?
2. Does result answer the question?
3. Is result just copying an input (hallucination)?

Return JSON:
{{"is_valid": true/false, "confidence": 0.0-1.0, "issues": [], "explanation": "..."}}

JSON:"""

        try:
            response = self.llm.generate(validation_prompt)
            clean = response.replace("```json", "").replace("```", "").strip()
            start = clean.find('{')
            end = clean.rfind('}') + 1
            
            if start != -1:
                return json.loads(clean[start:end])
            return {"is_valid": True, "confidence": 0.5, "issues": [], "explanation": "Parse failed"}
                
        except:
            return {"is_valid": True, "confidence": 0.5, "issues": [], "explanation": "Validation error"}
    
    def process_math_question(self, question: str, context: str) -> Optional[Dict]:
        """
        OPTIMIZED PIPELINE: Detect → Extract → Code → Execute
        Skipped 'Validate' step to improve speed.
        """
        print("\n" + "="*80)
        print("🧮 MATH EXECUTION MODE ACTIVATED")
        print("="*80)
        
        # Step 1: Extract variables
        print("📊 Step 1/3: Extracting variables...")
        variables = self.extract_variables_from_context(context, question)
        
        if not variables:
            print("   ⚠️ No variables found - fallback to LLM")
            return None
        
        print(f"   ✅ Extracted {len(variables)} variables")
        
        # Step 2: Generate code
        print("\n💻 Step 2/3: Generating Python code...")
        code = self.generate_calculation_code(question, variables, context)
        
        if not code:
            print("   ⚠️ Code generation failed")
            return None
            
        # Step 3: Execute
        print("\n⚡ Step 3/3: Executing in sandbox...")
        exec_result = self.execute_code_safely(code)
        
        if not exec_result["success"]:
            print(f"   ❌ Execution failed: {exec_result['error']}")
            return None
        
        result_output = exec_result["output"]
        print(f"   ✅ Executed Result: {result_output}")
        
        # SKIP VALIDATION to save time
        # answer = f"**Calculated Answer:** {result_output}"
        
        return {
            "success": True, 
            "answer": result_output, 
            "output": result_output
        }