"""
Test suite for Review questions to measure improvement.
"""
import requests
import json
import time

BASE_URL = "http://localhost:8000"

# These are the exact questions from the "Hostile Review"
test_cases = [
    {
        "name": "Review Test 2 - Arithmetic (The '213' Trap)",
        "question": "Calculate the Phase 3 Adjusted Load Index by summing Categories A (88), B (76), C (49), subtracting overlap (27), then dividing by effective records (start 12, discard 3, dormant 2, add splits 3, subtract merges 2, subtract equivalency 1)",
        "expected_keywords": ["26.57", "186", "7"], 
        "forbidden_keywords": ["213", "30.4"], # Common hallucinations
        "target_score": 95
    },
    {
        "name": "Entity Extraction Check (Simple)",
        "question": "What is the revenue for Apple in Q1 2024?",
        "expected_keywords": [], # Just checking if it runs without crashing
        "forbidden_keywords": [],
        "target_score": 100
    }
]

def run_test(test_case):
    print(f"\n{'='*80}")
    print(f"TEST: {test_case['name']}")
    print(f"{'='*80}")
    print(f"Question: {test_case['question'][:100]}...")

    start_time = time.time()
    try:
        response = requests.post(
            f"{BASE_URL}/query",
            json={"question": test_case['question'], "history": []},
            timeout=300 # Give it time for deep reasoning/math
        )

        elapsed = time.time() - start_time
        print(f"⏱️  Latency: {elapsed:.2f}s")

        if response.status_code == 200:
            data = response.json()
            answer = data['answer']
            confidence = data.get('confidence', 0)
            context = data.get('context_used', [])

            print(f"\n--- ANSWER ---")
            print(answer)
            print(f"\n--- DEBUG INFO ---")
            print(f"Confidence: {confidence}")
            print(f"Docs Retrieved: {len(context)}")

            # Validation Logic
            answer_lower = answer.lower()
            
            # Check Expected
            passed = False
            found_keywords = [k for k in test_case['expected_keywords'] if k in answer_lower]
            
            if test_case['expected_keywords']:
                if found_keywords:
                    print(f"✅ Found expected keywords: {found_keywords}")
                    passed = True
                else:
                    print(f"❌ Missing expected keywords: {test_case['expected_keywords']}")
            else:
                passed = True # No keywords to check (just a crash test)

            # Check Forbidden
            hit_forbidden = [k for k in test_case['forbidden_keywords'] if k in answer_lower]
            if hit_forbidden:
                print(f"❌ FOUND FORBIDDEN HALLUCINATION: {hit_forbidden}")
                passed = False

            print(f"\nRESULT: {'✅ PASS' if passed else '❌ FAIL'}")
            return passed
        else:
            print(f"\n❌ API ERROR: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        print(f"\n❌ EXCEPTION: {e}")
        return False

if __name__ == "__main__":
    print("🧪 DOCUMIND PHASE 1 VERIFICATION SUITE")
    print("="*80)
    print("Ensuring server is up...")
    try:
        requests.get(f"{BASE_URL}/documents", timeout=2)
        print("✅ Server is online")
    except:
        print("❌ Server is offline! Run 'python main.py' first.")
        exit()

    results = []
    for test in test_cases:
        passed = run_test(test)
        results.append((test['name'], passed))

    print(f"\n{'='*80}")
    print("📊 TEST SUMMARY")
    print(f"{'='*80}")
    for name, passed in results:
        print(f"{'✅' if passed else '❌'} {name}")