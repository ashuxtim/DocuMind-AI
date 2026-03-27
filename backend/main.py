"""
DocuMind FastAPI Application

Fixes applied (12 total):
  1  Dead imports removed         — ollama, pickle, networkx, shutil, StaticFiles (dead after Fix 12)
  2  CORS env var                 — CORS_ALLOWED_ORIGINS; wildcard as dev fallback
  3  Input validation             — QueryRequest.question min/max length + null byte check
  4  Lifespan lazy init           — storage, vector_db, kb, ingestor moved out of module level
  5  asyncio.wait_for timeout     — 504 on timeout; no custom executor needed
  6  /query HTTP 500 on exception — raises HTTPException(500) instead of returning 200 + error string
  7  Health check probes          — lightweight pings, always HTTP 200, status in body
  8  /delete StateManager method  — no direct redis_client access; stale ChromaDB comment fixed
  9  _get_document_list helper    — shared logic between /documents and _build_dashboard_data
  10 Dashboard Redis TTL cache    — 30s cache on graph data; invalidation in tasks.py on completion
  11 selected_docs wire-through   — confirmed present in inputs dict (no change needed)
  12 /summarize through agent     — full audit + fabrication detection pipeline; Flag A resolved
"""
import os
from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import re
from contextlib import asynccontextmanager
from typing import List, Optional, Dict

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from celery.result import AsyncResult
from vector_store import VectorStore
from ingest import DocuMindIngest
from knowledge_graph import KnowledgeBase
from celery_app import celery_app
from tasks import ingest_document_task
from state_manager import StateManager
from langsmith import traceable
from agent_graph import app_graph
from minio_storage import MinIOStorage

# ---------------------------------------------------------------------------
# Module-level state — None until lifespan initializes them.
# Access via getter functions (get_storage, get_vector_db, etc.) inside routes.
# ---------------------------------------------------------------------------
_storage:  Optional[MinIOStorage]   = None
_vector_db: Optional[VectorStore]   = None
_kb:       Optional[KnowledgeBase]  = None
_ingestor: Optional[DocuMindIngest] = None

# StateManager kept at module level — has lazy Redis reconnect; used by tasks.py
state_manager = StateManager()

# ---------------------------------------------------------------------------
# Fix 4 — Lifespan: heavy services initialize AFTER FastAPI starts serving.
# /health responds immediately even before Neo4j/Qdrant/MinIO are ready.
# Each service initializes independently — one failure doesn't block others.
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _storage, _vector_db, _kb, _ingestor

    print("⏳ Initializing services...")

    try:
        _storage = MinIOStorage()
        print("   ✅ MinIO ready")
    except Exception as e:
        print(f"   ⚠️ MinIO init failed: {e}")

    try:
        _vector_db = VectorStore()
        print("   ✅ Qdrant ready")
    except Exception as e:
        print(f"   ⚠️ Qdrant init failed: {e}")

    try:
        _kb = KnowledgeBase()
        print("   ✅ Neo4j ready")
    except Exception as e:
        print(f"   ⚠️ Neo4j init failed: {e}")

    try:
        _ingestor = DocuMindIngest()
        print("   ✅ Ingestor ready")
    except Exception as e:
        print(f"   ⚠️ Ingestor init failed: {e}")

    print("🚀 DocuMind started")
    yield
    print("🛑 DocuMind shutting down")


# ---------------------------------------------------------------------------
# Service getters — raise HTTP 503 if called before lifespan completes
# ---------------------------------------------------------------------------
def get_storage() -> MinIOStorage:
    if _storage is None:
        raise HTTPException(status_code=503, detail="Storage service not available")
    return _storage

def get_vector_db() -> VectorStore:
    if _vector_db is None:
        raise HTTPException(status_code=503, detail="Vector DB not available")
    return _vector_db

def get_kb() -> KnowledgeBase:
    if _kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")
    return _kb

def get_ingestor() -> DocuMindIngest:
    if _ingestor is None:
        raise HTTPException(status_code=503, detail="Ingestor not available")
    return _ingestor


# ---------------------------------------------------------------------------
# App + middleware
# ---------------------------------------------------------------------------
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Fix 2 — CORS from env var; "*" as dev fallback
ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")

app = FastAPI(title="DocuMind AI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Fix 10 — Dashboard graph cache constants
# Invalidation fires in tasks.py after process_document completes — not at
# upload dispatch, because the graph data hasn't changed until ingestion finishes.
# ---------------------------------------------------------------------------
DASHBOARD_CACHE_KEY = "cache:dashboard_graph"
DASHBOARD_CACHE_TTL = 30  # seconds


# ---------------------------------------------------------------------------
# Fix 3 — Request models with input validation
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    question:     str                            = Field(..., min_length=3, max_length=2000)
    history:      Optional[List[Dict[str, str]]] = []
    selected_docs: Optional[List[str]]           = []

    @validator("question")
    def no_null_bytes(cls, v):
        if "\x00" in v:
            raise ValueError("Invalid characters in question")
        return v.strip()


class QueryResponse(BaseModel):
    answer:       str
    context_used: List[str]
    confidence:   float
    model:        str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_mime_type(filename: str) -> str:
    """Return MIME type from filename extension."""
    ext = os.path.splitext(filename)[1].lower()
    mime_types = {
        ".pdf":  "application/pdf",
        ".txt":  "text/plain",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".md":   "text/markdown",
        ".html": "text/html",
        ".htm":  "text/html",
    }
    return mime_types.get(ext, "application/octet-stream")


def _get_document_list(all_statuses: dict) -> List[dict]:
    """
    Fix 9 — Shared helper: merge MinIO file list with Redis status data.
    Used by both /documents and _build_dashboard_data to avoid duplication.
    Returns full document info sorted newest-first.
    """
    storage = get_storage()
    documents = []

    for file_info in storage.list_files():
        filename  = file_info["filename"]
        file_size = file_info["size"]
        status_data = all_statuses.get(filename, {})

        documents.append({
            "filename":     filename,
            "status":       status_data.get("status", "completed"),
            "task_id":      status_data.get("task_id"),
            "uploaded_at":  status_data.get("uploaded_at"),
            "completed_at": status_data.get("completed_at"),
            "error":        status_data.get("error"),
            "size":         file_size,
            "type":         get_mime_type(filename),
            "url":          None,
        })

    documents.sort(
        key=lambda x: x["uploaded_at"] if x["uploaded_at"] else "0000",
        reverse=True,
    )
    return documents


def _build_dashboard_data() -> dict:
    """
    Read-only aggregation for the Dashboard UI.
    Every section wrapped in try/except — single service failure never crashes the endpoint.
    Graph data served from Redis cache (30s TTL) to avoid Neo4j load on every poll.
    """
    # ── 1. DOCUMENTS ──────────────────────────────────────────────────────
    doc_list    = []
    active_jobs = 0
    try:
        all_statuses = state_manager.get_all_statuses()
        doc_list     = _get_document_list(all_statuses)
        active_jobs  = sum(1 for d in doc_list if d["status"] == "processing")
    except Exception as e:
        print(f"⚠️ Dashboard: documents section failed: {e}")

    total_documents = len(doc_list)

    # ── 2. GRAPH INTELLIGENCE (Fix 10 — Redis-cached) ─────────────────────
    total_nodes    = 0
    total_links    = 0
    top_entities   = []
    relation_types = {}
    try:
        cached = state_manager.redis_client.get(DASHBOARD_CACHE_KEY)
        if cached:
            graph_data = json.loads(cached)
        else:
            graph_data = get_kb().get_visualization_data()
            state_manager.redis_client.setex(
                DASHBOARD_CACHE_KEY,
                DASHBOARD_CACHE_TTL,
                json.dumps(graph_data),
            )

        nodes       = graph_data.get("nodes", [])
        links       = graph_data.get("links", [])
        total_nodes = len(nodes)
        total_links = len(links)

        degree_map = {}
        for link in links:
            src = link.get("source", "")
            tgt = link.get("target", "")
            degree_map[src] = degree_map.get(src, 0) + 1
            degree_map[tgt] = degree_map.get(tgt, 0) + 1

        sorted_entities = sorted(degree_map.items(), key=lambda x: x[1], reverse=True)
        top_entities = [
            {"name": name, "connections": count}
            for name, count in sorted_entities[:6]
        ]

        for link in links:
            label = link.get("label", "UNKNOWN") or "UNKNOWN"
            relation_types[label] = relation_types.get(label, 0) + 1

    except Exception as e:
        print(f"⚠️ Dashboard: graph section failed: {e}")

    # ── 3. SYSTEM HEALTH ──────────────────────────────────────────────────
    redis_status = "unknown"
    try:
        if state_manager.redis_client and state_manager.redis_client.ping():
            redis_status = "connected"
        else:
            redis_status = "disconnected"
    except Exception:
        redis_status = "disconnected"

    neo4j_status = "unknown"
    try:
        kb = get_kb()
        if kb.driver:
            kb.driver.verify_connectivity()
            neo4j_status = "connected"
        else:
            neo4j_status = "disconnected"
    except Exception:
        neo4j_status = "disconnected"

    qdrant_status = "unknown"
    try:
        vdb = get_vector_db()
        if vdb.client:
            vdb.client.get_collections()
            qdrant_status = "connected"
        else:
            qdrant_status = "disconnected"
    except Exception:
        qdrant_status = "disconnected"

    llm_status = "unknown"
    try:
        ingestor = get_ingestor()
        if ingestor and ingestor.agent and ingestor.agent.llm:
            llm_status = "connected"
        else:
            llm_status = "disconnected"
    except Exception:
        llm_status = "disconnected"

    minio_status = "unknown"
    try:
        get_storage().client.list_buckets()
        minio_status = "connected"
    except Exception:
        minio_status = "disconnected"

    # ── 4. OVERVIEW ───────────────────────────────────────────────────────
    return {
        "overview": {
            "total_documents":  total_documents,
            "total_entities":   total_nodes,
            "total_relations":  total_links,
            "active_jobs":      active_jobs,
            "llm_provider":     os.getenv("LLM_PROVIDER", "Unknown"),
            "concurrency_mode": os.getenv("CONCURRENCY_MODE", "Local"),
        },
        "documents": doc_list,
        "graph": {
            "total_nodes":    total_nodes,
            "total_links":    total_links,
            "top_entities":   top_entities,
            "relation_types": relation_types,
        },
        "health": {
            "redis":  redis_status,
            "neo4j":  neo4j_status,
            "qdrant": qdrant_status,
            "llm":    llm_status,
            "minio":  minio_status,
        },
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/uploads/{filename}")
async def get_file(filename: str):
    """Stream file from MinIO to browser via FastAPI proxy."""
    storage = get_storage()
    try:
        response = storage.client.get_object(Bucket=storage.bucket, Key=filename)
        mime = get_mime_type(filename)
        return StreamingResponse(
            response["Body"],
            media_type=mime,
            headers={"Content-Disposition": f"inline; filename={filename}"},
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"File not found: {str(e)}")


@app.get("/health")
async def health_check():
    """
    Fix 7 — Lightweight dependency probes for Kubernetes liveness and readiness.
    Always returns HTTP 200 — per-service status in body.
    A degraded pod serving partial requests is better than a pod K8s stops routing to.
    503 on readiness probe marks ALL pods unready simultaneously on rolling deploy —
    worse than degraded. Let operators read the body; don't let K8s drop traffic.
    """
    checks: dict = {}

    # Redis — critical: StateManager depends on it
    try:
        if state_manager.redis_client and state_manager.redis_client.ping():
            checks["redis"] = "ok"
        else:
            checks["redis"] = "disconnected"
    except Exception as e:
        checks["redis"] = f"error: {str(e)[:60]}"

    # Neo4j — lightweight connectivity verify (no data load)
    try:
        if _kb and _kb.driver:
            _kb.driver.verify_connectivity()
            checks["neo4j"] = "ok"
        else:
            checks["neo4j"] = "not_initialized"
    except Exception as e:
        checks["neo4j"] = f"error: {str(e)[:60]}"

    # Qdrant — list_collections is the lightest available probe
    try:
        if _vector_db and _vector_db.client:
            _vector_db.client.get_collections()
            checks["qdrant"] = "ok"
        else:
            checks["qdrant"] = "not_initialized"
    except Exception as e:
        checks["qdrant"] = f"error: {str(e)[:60]}"

    # MinIO — list_buckets is fast; no data transfer
    try:
        if _storage:
            _storage.client.list_buckets()
            checks["minio"] = "ok"
        else:
            checks["minio"] = "not_initialized"
    except Exception as e:
        checks["minio"] = f"error: {str(e)[:60]}"

    all_ok = all(v == "ok" for v in checks.values())

    return JSONResponse(
        status_code=200,
        content={
            "status":  "healthy" if all_ok else "degraded",
            "service": "documind-backend",
            "version": os.getenv("APP_VERSION", "dev"),
            "checks":  checks,
        },
    )


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Saves the file to MinIO and dispatches a Celery task for ingestion.
    Returns a task_id immediately.
    Cache invalidation for dashboard graph happens in tasks.py on ingestion
    completion — NOT here, because the graph hasn't changed at dispatch time.
    """
    storage = get_storage()

    allowed_extensions = [".pdf", ".txt", ".docx", ".md", ".html", ".htm"]
    file_ext = os.path.splitext(file.filename)[1].lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}",
        )

    if storage.file_exists(file.filename):
        raise HTTPException(
            status_code=409,
            detail=f"File '{file.filename}' already exists. Please rename or delete it first.",
        )

    try:
        file.file.seek(0)
        storage.upload_file(file.filename, file.file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    task = ingest_document_task.delay(file.filename)
    state_manager.set_processing(file.filename, task.id)

    return {
        "message":  "Ingestion started",
        "filename": file.filename,
        "task_id":  task.id,
        "status":   "processing",
    }


@app.get("/status/{task_id}")
async def get_status(task_id: str):
    """Check the status of a specific ingestion task via Celery/Redis."""
    task_result = AsyncResult(task_id, app=celery_app)

    response: dict = {
        "task_id": task_id,
        "status":  task_result.status,
    }

    if task_result.ready():
        response["result"] = task_result.result

    if task_result.info:
        response["info"] = task_result.info

    return response


@app.post("/cancel/{filename}")
async def cancel_job(filename: str):
    """Triggers cooperative cancellation and graceful cleanup."""
    state_manager.set_cancelled(filename)

    status_data = state_manager.get_status(filename)
    if status_data and status_data.get("task_id"):
        celery_app.control.revoke(status_data["task_id"])

    return {"message": f"Cancellation requested for {filename}. Graceful cleanup initiated."}


@app.delete("/delete/{filename}")
async def delete_document(filename: str):
    """
    Removes the document from Vector DB, Graph DB, MinIO, and Redis state.
    """
    storage  = get_storage()
    ingestor = get_ingestor()
    results  = {"filename": filename, "steps": {}}

    # 1. Clean up Vector DB and Graph DB
    try:
        await ingestor.cleanup(filename)
        results["steps"]["memory"] = "deleted"
    except Exception as e:
        results["steps"]["memory"] = f"failed: {str(e)}"
        print(f"❌ Cleanup failed for {filename}: {e}")

    # 2. Delete from MinIO
    try:
        if storage.file_exists(filename):
            storage.delete_file(filename)
            results["steps"]["storage"] = "deleted"
        else:
            results["steps"]["storage"] = "not_found"
    except Exception as e:
        results["steps"]["storage"] = f"error: {str(e)}"

    # 3. Fix 8 — clean up Redis state via StateManager method
    # No direct redis_client access — encapsulation preserved
    try:
        state_manager.clear_document_state(filename)
        results["steps"]["state"] = "cleared"
    except Exception as e:
        results["steps"]["state"] = f"ignored: {str(e)}"

    return {"message": f"Deleted {filename}", "details": results}


@app.get("/documents")
def get_documents():
    """Returns list of documents with full metadata including ingestion status."""
    all_statuses = state_manager.get_all_statuses()
    return {"documents": _get_document_list(all_statuses)}


@app.get("/dashboard")
def get_dashboard():
    """
    Aggregates system-wide intelligence for the Dashboard UI.
    Read-only. No mutations. Safe to call at any frequency.
    """
    return _build_dashboard_data()


@app.get("/graph")
def get_graph(limit: int = 1000):
    """Returns graph visualization data for GraphExplorer component."""
    return get_kb().get_visualization_data(limit=limit)


@app.post("/query", response_model=QueryResponse)
@traceable(name="langgraph_rag")
async def query_knowledge_base(request: QueryRequest):
    """Executes the LangGraph RAG pipeline."""
    print(f"🧠 Invoking Agent Graph for: {request.question}")

    inputs = {
        "question":          request.question,
        "history":           request.history or [],
        "selected_docs":     request.selected_docs or [],  # Fix 11 — confirmed wired
        "sub_queries":       [],
        "documents":         [],
        "generation":        "",
        "audit_feedback":    "",
        "retry_count":       0,
        "sources":           [],
        "top_rerank_score":  0.0,
        "has_contradiction": False,
    }

    try:
        # Fix 5 — asyncio.wait_for; surfaces as 504 instead of hanging forever
        final_state = await asyncio.wait_for(
            asyncio.to_thread(app_graph.invoke, inputs),
            timeout=float(os.getenv("QUERY_TIMEOUT_S", "60")),
        )

        raw_answer = final_state["generation"]
        clean_answer = re.sub(
            r'\[[^\]]*SYSTEM NOTE:[^\]]*TRUSTED CODE EXECUTION RESULT[^\]]*\]',
            '',
            raw_answer,
        ).strip()
        return QueryResponse(
            answer=clean_answer,
            context_used=final_state.get("sources", []),
            confidence=(
                max(0.0, min(final_state.get("top_rerank_score", 0.5) * 0.7, 0.75))
                if final_state.get("has_contradiction", False)
                else max(0.05, min(final_state.get("top_rerank_score", 0.5), 0.95))
                if not final_state.get("audit_feedback", "")
                else max(0.05, min(final_state.get("top_rerank_score", 0.5) * 0.5, 0.5))
            ),
            model="DocuMind-Agent-v2",
        )

    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Query timed out — try a simpler question")

    except Exception as e:
        # Fix 6 — raise 500; monitoring systems see real failures, not 200 + error string
        print(f"❌ Graph Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/summarize/{filename}")
@traceable(name="document_summary")
async def summarize_document(filename: str):
    """
    Fix 12 — Routes summarization through the full agent graph pipeline.
    Summaries get fabrication detection, constraint checking, and LLM audit
    — same quality guarantees as /query.
    Replaces direct agent.llm.generate call which bypassed all audit stages.
    """
    print(f"📑 Generating Summary for: {filename}")

    summary_request = QueryRequest(
        question=(
            f"Provide a comprehensive executive summary of '{filename}'. "
            f"Include: key financial figures, main topics, any contradictions "
            f"or inconsistencies found in the document, and strategic highlights."
        ),
        history=[],
        selected_docs=[filename],
    )

    try:
        response = await query_knowledge_base(summary_request)
        return {"summary": response.answer}
    except Exception as e:
        return {"summary": f"Summary Error: {str(e)}"}
