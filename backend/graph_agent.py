import json
from typing import List, Dict, Any
from llm_provider import get_llm_provider
from langsmith import traceable

class GraphBuilder:
    def __init__(self):
        # 1. Get the configured provider (Ollama, OpenAI, vLLM, etc.)
        # This abstraction allows swapping hardware without changing this file.
        self.llm = get_llm_provider()
        self.model_name = self.llm.get_model_name()
        print(f"🤖 GraphBuilder initialized with: {self.model_name}")

    @traceable(name="graph_extraction")
    def extract_relationships(self, text_chunk: str) -> List[Dict[str, Any]]:
        """
        Extracts entities and relationships with TEMPORAL GROUNDING + CORROBORATION.
        """
        system_prompt = """You are a Financial Knowledge Graph Extraction Expert.

        EXTRACTION RULES:
        1. **Temporal Grounding**: EVERY numerical value MUST include its time period in the subject/object
        - ❌ BAD: {"subject": "Revenue", "object": "$10M"}
        - ✅ GOOD: {"subject": "Q1 2024 Revenue", "object": "$10M"}

        2. **Revision Detection**: If text says "restated", "revised", "corrected", "updated":
        - Use predicate: "REVISED_TO" or "SUPERSEDES"
        - Example: {"subject": "Q1 Original Revenue $8M", "predicate": "REVISED_TO", "object": "Q1 Restated Revenue $7M"}

        3. **Corroboration Strength**:
        - HIGH: Explicit in same sentence ("Revenue was $10M in Q1")
        - MEDIUM: Implied across sentences
        - LOW: Inferred from context

        4. **Entity Naming**: Be specific
        - Use "Apple Q1 2024 Revenue" not "Revenue"
        - Use "CEO as of Jan 2024" not "CEO"

        5. **Comparison Relations**: For "increased from X to Y":
        - {"subject": "Q1 Revenue", "predicate": "INCREASED_TO", "object": "Q2 Revenue", "period": "2024"}
        
        6. **Adversarial Detection (CRITICAL):**
            - If a statement explicitly **NEGATES**, **REVISES**, or **SUPERSEDES** a previous fact, you MUST use those exact verbs as the predicate.
            - Example: "The $10M figure was incorrect and restated to $8M."
              -> {"subject": "$10M", "predicate": "REVISED_TO", "object": "$8M", "corroboration": "HIGH"}
        
        OUTPUT FORMAT (JSON List):
        [
            {
                "subject": "Entity Name", 
                "predicate": "RELATIONSHIP_TYPE", 
                "object": "Target Entity/Value",
                "period": "Q1 2024",      // Optional, extract if present
                "corroboration": "HIGH"   // Optional, defaults to MEDIUM
            }
        ]
        """

        prompt = f"""Extract structured data from this text. 
        Focus on attaching TIME PERIODS and detecting CORROBORATION strength.
        
        Text:
        {text_chunk}
        
        Return JSON list only."""
        
        try:
            # print(f"      Verify: Sending {len(text_chunk)} chars to {self.model_name}...")
            response_text = self.llm.generate(prompt, system_prompt)
            
            clean_json = response_text.replace("```json", "").replace("```", "").strip()
            start = clean_json.find('[')
            end = clean_json.rfind(']') + 1
            
            if start != -1 and end != -1:
                json_str = clean_json[start:end]
                relations = json.loads(json_str)
                
                # Post-processing: Ensure 'corroboration' field exists
                for r in relations:
                    if 'corroboration' not in r:
                        r['corroboration'] = 'MEDIUM'  # Default safe value
                        
                return relations
                    
            return []

        except Exception as e:
            print(f"      ⚠️ Extraction Failed: {e}")
            return []
        
    @traceable(name="entity_extraction")
    def extract_query_entities(self, question: str) -> List[str]:
        """
        Uses the LLM to identify the key entities in a user's question for Graph Search.
        Example: "Who is the CEO of Google?" -> ["CEO", "Google"]
        """
        system_prompt = """Extract search keywords for a knowledge graph query.

        RULES:
        1. Extract proper nouns (companies, people, products)
        2. Extract key financial terms (revenue, EBITDA, ratio)
        3. Extract time periods (Q1, Q2, 2024, fiscal year)
        4. Extract action words (acquired, merged, revised)
        5. Ignore stop words (the, is, what, who)

        Return ONLY a JSON array of 3-8 keywords.
        Example: ["Apple", "iPhone", "Q1 2024", "revenue", "growth"]

        JSON array:"""

        try:
            response_text = self.llm.generate(question, system_prompt)
            
            # Clean up response
            clean_json = response_text.replace("```json", "").replace("```", "").strip()
            
            # Robust JSON extraction
            start = clean_json.find('[')
            end = clean_json.rfind(']') + 1
            
            if start != -1 and end != -1:
                return json.loads(clean_json[start:end])
            
            return []

        except Exception as e:
            print(f"Entity Extraction Error: {e}")
            return []