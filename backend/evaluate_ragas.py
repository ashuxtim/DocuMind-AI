"""
DocuMind RAGAS Evaluation Pipeline
Calls app_graph.invoke() directly to capture full AgentState including
retrieved document chunks. Uses NIM endpoints as judge LLM and embeddings.
"""

import os
import re
import sys
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import random

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
    answer_correctness,
)
from langchain_openai import ChatOpenAI
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
from langsmith import Client as LangSmithClient

from agent_graph import app_graph
from minio_storage import MinIOStorage
from vector_store import VectorStore


def _sanitize_for_json(obj):
    """Recursively replace float NaN/Inf with None for JSON safety."""
    if isinstance(obj, float):
        return None if (obj != obj or obj == float('inf') or obj == float('-inf')) else obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj


# ── Judge LLM and Embeddings (NIM, OpenAI-compatible) ──────────────────────
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NIM_BASE_URL   = "https://integrate.api.nvidia.com/v1"

def _build_judge_llm():
    provider = os.getenv("JUDGE_LLM_PROVIDER", "nvidia").lower()
    model = os.getenv("JUDGE_MODEL", "google/gemma-3-27b-it")
    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(
            api_key=os.getenv("GROQ_API_KEY"),
            model=model,
            temperature=0,
        )
    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=0,
        )
    else:  # nvidia / nim — default
        return ChatOpenAI(
            base_url=NIM_BASE_URL,
            api_key=os.getenv("NVIDIA_API_KEY"),
            model=model,
            temperature=0,
        )

judge_llm = _build_judge_llm()

JUDGE_EMBED_MODEL = os.getenv("JUDGE_EMBED_MODEL", "nvidia/nv-embedqa-e5-v5")

judge_embeddings = NVIDIAEmbeddings(
    api_key=NVIDIA_API_KEY,
    model=JUDGE_EMBED_MODEL,
)

# ── Ground Truth Dataset ────────────────────────────────────────────────────
EVAL_DATASET = [
    {
        "question": (
            "A Data Subject who is an EU client has formally exercised their "
            "right to erasure under the European privacy framework. Their records "
            "are 6 years old and are subject to FCA SYSC 9.1 record-keeping "
            "requirements. Must Meridian delete these records? If not, who holds "
            "the decision authority, what is the applicable exception, and what "
            "is the interim guidance currently in force?"
        ),
        "ground_truth": (
            "Meridian must not delete the records. The applicable exception is "
            "Article 17(3)(b) of the GDPR, which permits retention when necessary "
            "to comply with a legal obligation — specifically FCA SYSC 9.1. "
            "Addendum 2.1(d) mandates this outcome and no discretionary authority "
            "is required. The interim guidance states that for records under seven "
            "years old subject to FCA SYSC 9.1, erasure requests under GDPR "
            "Article 17 must be declined on the basis of the Article 17(3)(b) "
            "exception."
        ),
    },
    {
        "question": (
            "Meridian's newly incorporated Singapore subsidiary needs a regulatory "
            "addendum. Who is responsible for preparing it, what is the deadline, "
            "and if MAS regulations conflict with the existing Framework, which "
            "regulatory hierarchy rule applies — and is there a gap in the current "
            "Framework regarding this?"
        ),
        "ground_truth": (
            "The Legal Division is responsible for preparing the Singapore-specific "
            "regulatory addendum (Addendum 2.2), with a deadline of June 30, 2024. "
            "If MAS regulations conflict with the Framework, Section 1.2(c) applies "
            "by extension: mandatory statutory requirements in a jurisdiction prevail "
            "over conflicting Framework provisions. There is a documented gap: "
            "Framework v4.2 does not address Singapore's Securities and Futures Act "
            "2001 or MAS regulations, which Addendum 2.1(c) explicitly notes require "
            "separate treatment through the new addendum."
        ),
    },
    {
        "question": (
            "At what transaction value does Tier 3 data classification require "
            "mandatory data custodian designation, and how does this interact with "
            "the Applicable Threshold formula in Section 6.4? If the floor in "
            "Annex III paragraph 7 and the ceiling in Annex III paragraph 8 produce "
            "a conflict for a specific transaction type, who must be notified, "
            "within what timeframe, and which external firm must be engaged?"
        ),
        "ground_truth": (
            "Tier 3 data classification requires mandatory data custodian designation "
            "for transactions exceeding $10,000 under Section 3.3. This threshold "
            "operates independently of the Applicable Threshold formula in Section 6.4, "
            "which is calculated as the Firm's Tier 1 capital base multiplied by a "
            "transaction-category coefficient from Annex III, subject to a floor of "
            "£500,000 (Annex III paragraph 7) and a ceiling of £50,000,000 (Annex III "
            "paragraph 8). If the floor and ceiling produce a conflict for a specific "
            "transaction type, the Risk Team must be notified. The Framework does not "
            "specify a notification timeframe for this conflict and does not mandate "
            "engagement of an external firm — escalation is internal to the Risk Team."
        ),
    },
    {
        "question": (
            "According to the Merger Agreement, when does ownership of the DCA-7 "
            "algorithm transfer to MHCH? Identify and explain the direct contradiction "
            "between Section 2.2 and Section 8.3 on this question, and state what "
            "interim arrangement was agreed to bridge this conflict."
        ),
        "ground_truth": (
            "Section 2.2 states that all IP including the DCA-7 algorithm transfers "
            "to MHCH automatically and immediately upon closing pursuant to Article VII "
            "Section 7.1(a) of the Merger Agreement. Section 8.3 directly contradicts "
            "this by requiring a minimum 90-day (and potentially up to 180-day) ITAR "
            "regulatory review by the Directorate of Defense Trade Controls before the "
            "DCA-7 transfer can be completed. The interim arrangement agreed to bridge "
            "this conflict is the IP Bridge Agreement, which grants MHCH an operational "
            "license to use the DCA-7 algorithm during the ITAR regulatory review period "
            "pending formal ownership transfer."
        ),
    },
    {
        "question": (
            "The Executive Summary states the transaction represents a multiple of "
            "8.7x TTM EBITDA. Section 4.2 calculates TTM EBITDA as $13,045,000. "
            "At a transaction value of $175,000,000, what is the actual multiple, "
            "and what explains the discrepancy between this figure and the 8.7x "
            "stated in Section 1?"
        ),
        "ground_truth": (
            "The actual EBITDA multiple is approximately 13.4x, calculated as "
            "$175,000,000 divided by $13,045,000. Section 4.2 itself states this "
            "figure explicitly: the enterprise value represents a multiple of "
            "approximately 13.4x TTM EBITDA, which is at the upper end but within "
            "the range of comparable transactions. The 8.7x figure stated in the "
            "Executive Summary in Section 1 is factually incorrect given the TTM "
            "EBITDA calculation in Section 4.2 and the $175M transaction value. "
            "The document does not explain the basis for the 8.7x figure."
        ),
    },
    {
        "question": (
            "The DCA-7 algorithm is subject to both active litigation and an ITAR "
            "regulatory challenge. What is the total escrow amount reserved "
            "specifically for these two risks, who holds the escrow, who represents "
            "Vantage Systems in the litigation, and what is the post-closing role "
            "of the person responsible for the algorithm's legal defense?"
        ),
        "ground_truth": (
            "The total escrow reserved for the two DCA-7 risks is $7,000,000: "
            "$5,000,000 in IP Regulatory Escrow for the ITAR challenge and "
            "$2,000,000 in Litigation Reserve for the DataBridge Holdings litigation. "
            "The escrow is held by Riverside Trust & Escrow Services, LLC. "
            "Vantage Systems is represented in the DataBridge litigation by "
            "Drakewood & Finch LLP, specifically partner Ms. Isabelle Drakewood-Chen, "
            "Esq. The person responsible for the algorithm's legal defense is "
            "Mr. James Wellbrook, Vantage's General Counsel, whose post-closing role "
            "is a 90-day transition period at his current compensation rate to assist "
            "with contract assignment, pending litigation, and legal documentation "
            "handover to MHCH's in-house legal team."
        ),
    },
]


# ── Dynamic dataset generation / persistence ─────────────────────────────────

DATASET_MINIO_KEY = "eval_dataset/latest.json"
QUESTIONS_PER_DOC = 2  # how many Q+GT pairs to generate per ingested document


def _generate_eval_dataset(vs: "VectorStore") -> list[dict]:
    """
    Discover all ingested documents, sample chunks, and use the judge LLM
    to generate Q+GT pairs grounded in the actual content.
    Returns a list of {"question": ..., "ground_truth": ...} dicts.
    """
    sources = vs.list_sources()
    if not sources:
        raise RuntimeError("No documents found in Qdrant — ingest documents before generating eval dataset.")

    print(f"  Found {len(sources)} document(s): {sources}")
    pairs = []

    generation_prompt = (
        "You are an expert evaluator for a document intelligence system. "
        "Given the following text chunks from a document, generate exactly {k} "
        "question-and-ground-truth pairs that test precise factual retrieval. "
        "Questions must be answerable purely from the provided chunks. "
        "Ground truths must be specific, complete, and faithful to the text.\n\n"
        "Respond ONLY with a JSON array with no preamble or markdown fences. "
        "Format: [{\"question\": \"...\", \"ground_truth\": \"...\"}, ...]\n\n"
        "Chunks:\n{chunks}"
    )

    def _process_source(source: str) -> list[dict]:
        try:
            all_chunks = vs.scroll_by_filename(source)
            if not all_chunks:
                print(f"  ⚠️  No chunks found for {source}, skipping.")
                return []
            sample = random.sample(all_chunks, min(8, len(all_chunks)))
            chunk_text = "\n\n---\n\n".join(c["text"] for c in sample)
            prompt = (
                generation_prompt
                .replace("{k}", str(QUESTIONS_PER_DOC))
                .replace("{chunks}", chunk_text)
            )
            response = judge_llm.invoke(prompt)
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            generated = json.loads(raw)
            result = [
                item for item in generated
                if "question" in item and "ground_truth" in item
            ]
            print(f"  ✅ {source}: generated {len(result)} pair(s)")
            return result
        except Exception as e:
            print(f"  ⚠️  Failed to generate for {source}: {e}")
            print(f"  ⚠️  Raw LLM response was: {raw[:500] if 'raw' in dir() else '<not set>'}")
            return []

    from concurrent.futures import ThreadPoolExecutor as _TPE
    with _TPE(max_workers=3) as pool:
        results = list(pool.map(_process_source, sources))
    pairs = [item for sublist in results for item in sublist]
    return pairs


def _load_eval_dataset(minio: "MinIOStorage") -> list[dict]:
    """Load the eval dataset from MinIO. Falls back to hardcoded EVAL_DATASET."""
    try:
        data = minio.download_json(DATASET_MINIO_KEY)
        if data is None:
            print(
                f"  ⚠️  No eval dataset found at {DATASET_MINIO_KEY}. "
                "Run with regenerate=true first to generate a dataset "
                "from your ingested documents. Falling back to hardcoded dataset — "
                "scores will be meaningless if your documents differ from the "
                "hardcoded questions."
            )
            return EVAL_DATASET
        pairs = data.get("pairs", [])
        print(f"  ✅ Loaded {len(pairs)} pair(s) from MinIO ({DATASET_MINIO_KEY})")
        return pairs
    except Exception as e:
        print(f"  ⚠️  Could not load from MinIO ({e}), falling back to hardcoded dataset.")
        return EVAL_DATASET


def _save_eval_dataset(minio: "MinIOStorage", pairs: list[dict]) -> None:
    """Save generated dataset to MinIO (versioned + latest)."""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    payload = {"generated_at": timestamp, "count": len(pairs), "pairs": pairs}
    minio.upload_json(f"eval_dataset/{timestamp}.json", payload)
    minio.upload_json(DATASET_MINIO_KEY, payload)
    print(f"  ✅ Saved eval dataset to MinIO: eval_dataset/{timestamp}.json + latest")


# ── Helpers ─────────────────────────────────────────────────────────────────

def _strip_metadata(chunk: str) -> str:
    """Remove [Source: X | Section: Y | Pg Z | Score: S] prefix from chunks."""
    return re.sub(r"^\[Source:[^\]]+\]\n?", "", chunk).strip()


def run_single_query(graph, question: str, selected_docs: list = None):
    """Run the LangGraph pipeline directly and return answer + raw chunks."""
    inputs = {
        "question":          question,
        "history":           [],
        "selected_docs":     selected_docs or [],
        "sub_queries":       [],
        "documents":         [],
        "generation":        "",
        "audit_feedback":    "",
        "retry_count":       0,
        "sources":           [],
        "top_rerank_score":  0.0,
        "has_contradiction": False,
    }
    final_state = graph.invoke(inputs)
    answer   = final_state.get("generation", "")
    raw_docs = final_state.get("documents", [])
    contexts = [_strip_metadata(d) for d in raw_docs if d.strip()]
    sources  = final_state.get("sources", [])
    score    = final_state.get("top_rerank_score", 0.0)
    q_type   = final_state.get("question_type", "unknown")
    return {
        "answer":   answer,
        "contexts": contexts,
        "sources":  sources,
        "score":    score,
        "q_type":   q_type,
    }


# ── Task entry point ─────────────────────────────────────────────────────────

def run_as_task(regenerate: bool = False):
    eval_rows = {
        "question":     [],
        "answer":       [],
        "contexts":     [],
        "ground_truth": [],
    }
    run_metadata = []

    def _run_one(args):
        idx, item = args
        q  = item["question"]
        gt = item["ground_truth"]
        try:
            res = run_single_query(app_graph, q)
            return (idx, q, gt, res, None)
        except Exception as exc:
            return (idx, q, gt, None, exc)

    # ── Dataset resolution ──────────────────────────────────────────────
    minio = MinIOStorage()
    vs = VectorStore()
    if regenerate:
        print("\n🔄 Regenerating eval dataset from ingested documents...")
        active_dataset = _generate_eval_dataset(vs)
        if not active_dataset:
            raise RuntimeError("Dataset generation produced 0 pairs. Aborting.")
        _save_eval_dataset(minio, active_dataset)
    else:
        print("\n📂 Loading eval dataset from MinIO...")
        active_dataset = _load_eval_dataset(minio)
    print(f"  Running evaluation on {len(active_dataset)} question(s).\n")
    # ───────────────────────────────────────────────────────────────────

    # ── Parallel query collection (3-way concurrent) ─────────────────────────
    raw_results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(_run_one, (i, item)): i
            for i, item in enumerate(active_dataset, 1)
        }
        for future in as_completed(futures):
            raw_results.append(future.result())

    # ── Fill eval_rows in original question order ─────────────────────────────
    raw_results.sort(key=lambda x: x[0])  # sort by question index

    for idx, q, gt, result, err in raw_results:
        if err is None:
            eval_rows["question"].append(q)
            eval_rows["answer"].append(result["answer"])
            eval_rows["contexts"].append(result["contexts"])
            eval_rows["ground_truth"].append(gt)
            run_metadata.append({
                "question_index": idx,
                "question_type":  result["q_type"],
                "num_chunks":     len(result["contexts"]),
                "top_score":      result["score"],
                "sources":        result["sources"],
            })
        else:
            eval_rows["question"].append(q)
            eval_rows["answer"].append("")
            eval_rows["contexts"].append([])
            eval_rows["ground_truth"].append(gt)
            run_metadata.append({"question_index": idx, "error": str(err)})

    # ── RAGAS scoring ────────────────────────────────────────────────────────
    dataset = Dataset.from_dict(eval_rows)

    METRIC_COLS = [
        "faithfulness", "answer_relevancy", "context_precision",
        "context_recall", "answer_correctness",
    ]

    import time as _time

    MAX_EVAL_RETRIES = 2
    ragas_result = None
    for _attempt in range(MAX_EVAL_RETRIES + 1):
        ragas_result = evaluate(
            dataset=dataset,
            metrics=[
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
                answer_correctness,
            ],
            llm=judge_llm,
            embeddings=judge_embeddings,
            batch_size=3,
            raise_exceptions=False,
        )
        df = ragas_result.to_pandas()
        nan_count = df[METRIC_COLS].isna().sum().sum()
        if nan_count == 0:
            break
        if _attempt < MAX_EVAL_RETRIES:
            print(
                f"  ⚠️  RAGAS attempt {_attempt + 1}: {nan_count} NaN score(s) detected "
                f"— retrying in 10s..."
            )
            _time.sleep(10)
        else:
            print(
                f"  ⚠️  RAGAS final attempt: {nan_count} NaN score(s) remain — "
                "possible judge LLM rate limit or partial failure. "
                "Results will contain None values for affected questions."
            )

    # ── Build result dict ────────────────────────────────────────────────────
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    iso_ts    = datetime.utcnow().isoformat() + "Z"

    metric_cols = METRIC_COLS

    metrics = {}
    for col in metric_cols:
        if col in df.columns:
            raw_val = df[col].mean()
            val = float(raw_val) if raw_val is not None else float("nan")
            metrics[col] = None if val != val else round(val, 4)

    per_question = []
    for i, row in df.iterrows():
        entry = {"index": i + 1}
        for col in metric_cols:
            if col in df.columns:
                raw_val = row[col]
                val = float(raw_val) if raw_val is not None else float("nan")
                entry[col] = None if val != val else round(val, 4)
        meta = run_metadata[i] if i < len(run_metadata) else {}
        entry["question_type"] = meta.get("question_type", "unknown")
        entry["num_chunks"]    = meta.get("num_chunks", 0)
        entry["top_score"]     = meta.get("top_score", 0.0)
        per_question.append(entry)

    result = {
        "timestamp":         iso_ts,
        "metrics":           metrics,
        "per_question":      per_question,
        "langsmith_dataset": f"DocuMind_RAGAS_{timestamp}",
    }

    result = _sanitize_for_json(result)

    # ── Save to MinIO ────────────────────────────────────────────────────────
    minio = MinIOStorage()
    minio.upload_json(f"evaluations/{timestamp}.json", result)
    minio.upload_json("evaluations/latest.json", result)

    # ── LangSmith upload ─────────────────────────────────────────────────────
    langsmith_key = os.getenv("LANGCHAIN_API_KEY")
    if langsmith_key:
        try:
            ls_client    = LangSmithClient(api_key=langsmith_key)
            dataset_name = f"DocuMind_RAGAS_{timestamp}"
            ls_dataset   = ls_client.create_dataset(
                dataset_name=dataset_name,
                description=f"RAGAS evaluation — {len(active_dataset)} queries",
            )
            ls_client.create_examples(
                inputs=[{"question": row["question"]} for row in active_dataset],
                outputs=[
                    {
                        "ground_truth": row["ground_truth"],
                        "answer":       eval_rows["answer"][i],
                    }
                    for i, row in enumerate(active_dataset)
                ],
                dataset_id=ls_dataset.id,
            )
        except Exception:
            pass

    return result


if __name__ == "__main__":
    import pprint
    result = run_as_task()
    pprint.pprint(result)
