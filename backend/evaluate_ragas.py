import os
import asyncio
import httpx
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy

# --- LANGCHAIN INTEGRATIONS ---
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_openai import ChatOpenAI 
from dotenv import load_dotenv

# --- IMPORT YOUR APP STACK ---
from vector_store import VectorStore
from llm_provider import get_llm_provider

load_dotenv()

# --- CONFIGURATION ---
# Tunnel Port from your r1.sh
CLOUD_BASE_URL = "http://localhost:8001/v1" 
LOCAL_OLLAMA_URL = "http://localhost:11434"

# --- TEST SETTINGS ---
# We filter by this filename to simulate "Selecting a Document"
TEST_FILENAME = "r1.txt"  # <--- CHANGE THIS to the file you want to test (e.g. "manual.pdf")

# Define the Questions & Answers for that specific file
test_data = [
    {
        "question": "Which port maps to the cloud?",
        "ground_truth": "Local port 8001 maps to cloud port 8000.", 
    },
    {
        "question": "What is the fallback if cloud fails?",
        "ground_truth": "It falls back to local Ollama on port 11434.",
    }
]

def fetch_dynamic_model_name(base_url, api_key="EMPTY"):
    """
    Pings the /models endpoint to get the EXACT model ID string.
    """
    try:
        print(f"🕵️  Asking {base_url} for active models...")
        response = httpx.get(
            f"{base_url}/models", 
            timeout=3.0, 
            headers={"Authorization": f"Bearer {api_key}"}
        )
        
        if response.status_code == 200:
            data = response.json()
            # vLLM/OpenAI format: {"data": [{"id": "Qwen/Qwen2.5-..."}]}
            # Ollama format: {"models": [{"name": "qwen2.5:7b"}]}
            
            if "data" in data and len(data["data"]) > 0:
                model_id = data["data"][0]["id"]
                print(f"   ✅ Found Model ID: {model_id}")
                return model_id
            
            if "models" in data and len(data["models"]) > 0:
                # Handle newer Ollama response structure
                m = data["models"][0]
                model_id = m.get("model") or m.get("name")
                print(f"   ✅ Found Model ID: {model_id}")
                return model_id
                
    except Exception as e:
        print(f"   ⚠️  Could not fetch models from {base_url}: {e}")
    
    return None

def get_dynamic_judge():
    """
    1. Tries Cloud Tunnel (8001).
    2. Falls back to Local Ollama (11434).
    Returns a LangChain Chat Object configured with the CORRECT name.
    """
    
    # 1. TRY CLOUD (vLLM)
    cloud_model_id = fetch_dynamic_model_name(CLOUD_BASE_URL)
    if cloud_model_id:
        print(f"   🚀 Using CLOUD Judge: {cloud_model_id}")
        return ChatOpenAI(
            base_url=CLOUD_BASE_URL,
            api_key="EMPTY",
            model=cloud_model_id, # Uses the exact string from the server
            temperature=0
        )

    # 2. FALLBACK TO LOCAL (OLLAMA)
    print("   ⚠️  Cloud unavailable. Checking Local Ollama...")
    local_model_id = fetch_dynamic_model_name(LOCAL_OLLAMA_URL)
    
    # Default to generic if auto-detect fails
    final_local_model = local_model_id if local_model_id else "qwen2.5:7b"
    
    print(f"   💻 Using LOCAL Judge: {final_local_model}")
    return ChatOllama(model=final_local_model, temperature=0)

# Initialize Components
vector_db = VectorStore()
app_llm = get_llm_provider() 
judge_embeddings = OllamaEmbeddings(model="nomic-embed-text") 

async def run_test_suite():
    # 1. GET THE JUDGE (With Dynamic Name)
    judge_llm = get_dynamic_judge()
    
    print(f"\n🧪 Starting Ragas Evaluation on file: '{TEST_FILENAME}'")
    results_data = {
        "question": [],
        "answer": [],
        "contexts": [],
        "ground_truth": []
    }

    # 2. RUN PIPELINE
    for item in test_data:
        q = item["question"]
        print(f"   running: {q}...")

        # A. RETRIEVAL (With Filter!)
        # We assume your VectorStore.search supports filters. 
        # If not, it just searches everything (fallback).
        # Typically: filters={"source": TEST_FILENAME}
        try:
            search_res = vector_db.search(q, limit=3, filters={"source": TEST_FILENAME})
        except TypeError:
            # Fallback if your search() method signature doesn't support filters yet
            search_res = vector_db.search(q, limit=3)
            
        retrieved_texts = [r["text"] for r in search_res]
        
        # B. GENERATION
        context_block = "\n".join(retrieved_texts)
        prompt = f"Answer based on context:\n{context_block}\n\nQuestion: {q}"
        generated_answer = app_llm.generate(prompt)

        # C. STORE
        results_data["question"].append(q)
        results_data["answer"].append(generated_answer)
        results_data["contexts"].append(retrieved_texts)
        results_data["ground_truth"].append(item["ground_truth"])

    # 3. EVALUATE
    dataset = Dataset.from_dict(results_data)
    
    print("   ⚖️  Grading answers...")
    scores = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy],
        llm=judge_llm, 
        embeddings=judge_embeddings
    )

    print("\n✅ Evaluation Report:")
    df = scores.to_pandas()
    
    # SAFE PRINT: Print all columns instead of guessing names
    print(df) 
    
    # Save to CSV (so you can open it in Excel/VS Code to see the scores)
    df.to_csv("ragas_report.csv", index=False)
    print("\n📄 Full report saved to 'ragas_report.csv'")

if __name__ == "__main__":
    asyncio.run(run_test_suite())