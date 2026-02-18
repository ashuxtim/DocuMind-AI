import os
from dotenv import load_dotenv
load_dotenv()
import shutil
import pickle
import networkx as nx
import asyncio
import re
from typing import List, Optional, Dict
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ollama import Client
from celery.result import AsyncResult # NEW: Task Status
from qdrant_client.models import Filter, FieldCondition, MatchValue
from vector_store import VectorStore
from ingest import DocuMindIngest
from graph_agent import GraphBuilder
from knowledge_graph import KnowledgeBase
from celery_app import celery_app # NEW: Celery Config
from tasks import ingest_document_task # NEW: The Worker Task
from state_manager import state_manager
from fastapi.staticfiles import StaticFiles
from langsmith import traceable
from agent_graph import app_graph

# --- CONFIGURATION ---
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="DocuMind AI")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- GLOBAL INSTANCES ---
# 1. NEW: Vector DB (Qdrant) - Used for Query/Search
vector_db = VectorStore()

# 2. Ingestor (For cleanup & graph access)
# Note: DocuMindIngest now uses VectorStore internally too
ingestor_read = DocuMindIngest() 
kb = KnowledgeBase()
agent = ingestor_read.agent 

# --- DATA MODELS ---
class QueryRequest(BaseModel):
    question: str
    history: Optional[List[Dict[str, str]]] = []
    selected_docs: Optional[List[str]] = []

class QueryResponse(BaseModel):
    answer: str
    context_used: List[str]
    confidence: float
    model: str

# --- ENDPOINTS ---

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Saves the file and dispatches a Celery task for ingestion.
    Returns a task_id immediately.
    """
    # Validate file type
    allowed_extensions = ['.pdf', '.txt', '.docx']
    file_ext = os.path.splitext(file.filename)[1].lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # Check if file already exists
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    if os.path.exists(file_path):
        raise HTTPException(
            status_code=409,
            detail=f"File '{file.filename}' already exists. Please rename or delete the existing file."
        )
    
    # Save file to disk
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    
    # DISPATCH CELERY TASK
    task = ingest_document_task.delay(file_path, file.filename)
    
    # TRACK STATE IN REDIS
    state_manager.set_processing(file.filename, task.id)
    
    return {
        "message": "Ingestion started",
        "filename": file.filename,
        "task_id": task.id,
        "status": "processing"
    }


@app.get("/status/{task_id}")
async def get_status(task_id: str):
    """
    Check the status of a specific ingestion task via Celery/Redis.
    """
    task_result = AsyncResult(task_id, app=celery_app)
    
    response = {
        "task_id": task_id,
        "status": task_result.status, # PENDING, STARTED, SUCCESS, FAILURE, REVOKED
    }

    # If the task returned a result (e.g. metadata or error)
    if task_result.ready():
        response["result"] = task_result.result
    
    # If the task has custom meta info (like progress updates)
    if task_result.info:
         response["info"] = task_result.info

    return response

@app.post("/cancel/{filename}")
async def cancel_job(filename: str):
    """
    Triggers cooperative cancellation and graceful cleanup.
    """
    # 1. Update Redis state to 'cancelled'. The worker token will catch this.
    state_manager.set_cancelled(filename)
    
    # 2. Revoke from Celery queue (ONLY for pending tasks, NO terminate=True)
    status_data = state_manager.get_status(filename)
    if status_data and status_data.get("task_id"):
        celery_app.control.revoke(status_data["task_id"])
        
    return {"message": f"Cancellation requested for {filename}. Graceful cleanup initiated."}

@app.delete("/delete/{filename}")
async def delete_document(filename: str):
    """
    Removes the document from Vector DB, Graph DB, Disk, and Redis State.
    """
    results = {"filename": filename, "steps": {}}

    # 1. Clean up "Memories" (ChromaDB & Neo4j)
    # We await this directly since the function is now async
    try:
        await ingestor_read.cleanup(filename)
        results["steps"]["memory"] = "deleted"
    except Exception as e:
        results["steps"]["memory"] = f"failed: {str(e)}"
        print(f"❌ Cleanup failed for {filename}: {e}")

    # 2. Delete Physical File
    file_path = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            results["steps"]["disk"] = "deleted"
        except Exception as e:
            results["steps"]["disk"] = f"error: {str(e)}"
    else:
        results["steps"]["disk"] = "not_found"

    # 3. Clean up Redis State (Status Tracking)
    # We attempt to remove the 'processing/completed' status so it doesn't linger
    try:
        # Assuming state_manager has a delete or we access the underlying redis
        # If your state_manager class doesn't have delete_task, you can add it
        # or simply ignore this if get_documents() relies solely on os.listdir()
        if hasattr(state_manager, 'delete_task'):
             state_manager.delete_task(filename)
             results["steps"]["state"] = "cleared"
    except Exception as e:
        results["steps"]["state"] = f"ignored: {str(e)}"

    return {"message": f"Deleted {filename}", "details": results}

@app.get("/documents")
def get_documents():
    """
    Returns a list of documents with full metadata including status.
    """
    if not os.path.exists(UPLOAD_DIR):
        return {"documents": []}
    
    # Get all statuses from Redis
    all_statuses = state_manager.get_all_statuses()
    
    documents = []
    
    # List all files in the uploads folder
    files = [
        f for f in os.listdir(UPLOAD_DIR)
        if os.path.isfile(os.path.join(UPLOAD_DIR, f))
    ]
    
    for filename in files:
        file_path = os.path.join(UPLOAD_DIR, filename)
        
        # Get file stats
        try:
            stat_info = os.stat(file_path)
            file_size = stat_info.st_size
        except:
            file_size = 0
        
        # Get status from Redis
        status_data = all_statuses.get(filename)
        
        if status_data:
            # We have status tracking
            doc_info = {
                "filename": filename,
                "status": status_data.get("status", "unknown"),
                "task_id": status_data.get("task_id"),
                "uploaded_at": status_data.get("uploaded_at"),
                "completed_at": status_data.get("completed_at"),
                "error": status_data.get("error"),
                "size": file_size,
                "type": get_mime_type(filename)
            }
            
            # Only provide URL if completed
            if status_data.get("status") == "completed":
                doc_info["url"] = f"/uploads/{filename}"
            else:
                doc_info["url"] = None
        else:
            # File exists but no status (orphaned or pre-migration)
            doc_info = {
                "filename": filename,
                "status": "completed",
                "task_id": None,
                "uploaded_at": None,
                "completed_at": None,
                "error": None,
                "size": file_size,
                "type": get_mime_type(filename),
                "url": f"/uploads/{filename}"
            }
        
        documents.append(doc_info)
    
    # Sort by upload time (newest first)
    documents.sort(
        key=lambda x: x["uploaded_at"] if x["uploaded_at"] else "0000", 
        reverse=True
    )
    
    return {"documents": documents}


def get_mime_type(filename: str) -> str:
    """Helper to get MIME type from filename"""
    ext = os.path.splitext(filename)[1].lower()
    mime_types = {
        '.pdf': 'application/pdf',
        '.txt': 'text/plain',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    }
    return mime_types.get(ext, 'application/octet-stream')

def _build_dashboard_data() -> dict:
    """
    Read-only aggregation of existing services for the dashboard.
    Every section is wrapped in try/except so a single service failure
    never crashes the endpoint.
    """

    # ── 1. DOCUMENTS (reuse /documents logic) ──────────────────────
    doc_list = []
    active_jobs = 0
    try:
        all_statuses = state_manager.get_all_statuses()
        files = [
            f for f in os.listdir(UPLOAD_DIR)
            if os.path.isfile(os.path.join(UPLOAD_DIR, f))
        ]
        for filename in files:
            file_path = os.path.join(UPLOAD_DIR, filename)
            try:
                file_size = os.stat(file_path).st_size
            except Exception:
                file_size = 0

            status_data = all_statuses.get(filename, {})
            status = status_data.get("status", "completed")
            if status == "processing":
                active_jobs += 1

            doc_list.append({
                "filename": filename,
                "status": status,
                "uploaded_at": status_data.get("uploaded_at"),
                "size": file_size,
            })

        doc_list.sort(
            key=lambda x: x["uploaded_at"] if x["uploaded_at"] else "0000",
            reverse=True,
        )
    except Exception as e:
        print(f"⚠️ Dashboard: documents section failed: {e}")

    total_documents = len(doc_list)

    # ── 2. GRAPH INTELLIGENCE ──────────────────────────────────────
    total_nodes = 0
    total_links = 0
    top_entities = []
    relation_types = {}
    try:
        graph_data = kb.get_visualization_data()
        nodes = graph_data.get("nodes", [])
        links = graph_data.get("links", [])
        total_nodes = len(nodes)
        total_links = len(links)

        # Top entities by degree
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

        # Relation type frequency
        for link in links:
            label = link.get("label", "UNKNOWN") or "UNKNOWN"
            relation_types[label] = relation_types.get(label, 0) + 1
    except Exception as e:
        print(f"⚠️ Dashboard: graph section failed: {e}")

    # ── 3. SYSTEM HEALTH ───────────────────────────────────────────
    # Redis
    redis_status = "unknown"
    try:
        if state_manager.redis_client and state_manager.redis_client.ping():
            redis_status = "connected"
        else:
            redis_status = "disconnected"
    except Exception:
        redis_status = "disconnected"

    # Neo4j
    neo4j_status = "unknown"
    try:
        if kb.driver:
            kb.driver.verify_connectivity()
            neo4j_status = "connected"
        else:
            neo4j_status = "disconnected"
    except Exception:
        neo4j_status = "disconnected"

    # Qdrant
    qdrant_status = "unknown"
    try:
        if vector_db.client:
            vector_db.client.get_collections()
            qdrant_status = "connected"
        else:
            qdrant_status = "disconnected"
    except Exception:
        qdrant_status = "disconnected"

    # LLM
    llm_status = "unknown"
    try:
        if agent and agent.llm:
            llm_status = "connected"
        else:
            llm_status = "disconnected"
    except Exception:
        llm_status = "disconnected"

    # ── 4. OVERVIEW ────────────────────────────────────────────────
    llm_provider = os.getenv("LLM_PROVIDER", "Unknown")
    concurrency_mode = os.getenv("CONCURRENCY_MODE", "Local")

    return {
        "overview": {
            "total_documents": total_documents,
            "total_entities": total_nodes,
            "total_relations": total_links,
            "active_jobs": active_jobs,
            "llm_provider": llm_provider,
            "concurrency_mode": concurrency_mode,
        },
        "documents": doc_list,
        "graph": {
            "total_nodes": total_nodes,
            "total_links": total_links,
            "top_entities": top_entities,
            "relation_types": relation_types,
        },
        "health": {
            "redis": redis_status,
            "neo4j": neo4j_status,
            "qdrant": qdrant_status,
            "llm": llm_status,
        },
    }

@app.get("/dashboard")
def get_dashboard():
    """
    Aggregates system-wide intelligence for the Dashboard UI.
    Read-only. No mutations. Safe to call at any frequency.
    """
    return _build_dashboard_data()

@app.get("/graph")
def get_graph(limit: int = 1000):
    """
    Returns graph visualization data for GraphExplorer component.
    """
    return kb.get_visualization_data(limit=limit)

@app.post("/query", response_model=QueryResponse)
@traceable(name="langgraph_rag")
async def query_knowledge_base(request: QueryRequest):
    """
    Executes the LangGraph RAG pipeline.
    """
    print(f"🧠 Invoking Agent Graph for: {request.question}")

    # 1. Prepare Initial State
    inputs = {
        "question": request.question,
        "history": request.history or [],
        "documents": [],
        "generation": "",
        "audit_feedback": "",
        "retry_count": 0,
        "sources": []
    }

    try:
        # 2. Invoke the Graph
        # We use .invoke() for synchronous execution (or .ainvoke for async if supported by your LLM provider wrapper)
        # Since your llm_provider seems synchronous for now, we use invoke inside a thread or directly.
        # Ideally, make your LLM provider async, but for now:
        final_state = await asyncio.to_thread(app_graph.invoke, inputs)
        
        return QueryResponse(
            answer=final_state["generation"],
            context_used=final_state.get("sources", []),
            confidence=1.0 if not final_state.get("audit_feedback") else 0.5,
            model="DocuMind-Agent-v2"
        )

    except Exception as e:
        print(f"❌ Graph Error: {e}")
        return QueryResponse(
            answer=f"An error occurred while processing your request: {str(e)}",
            context_used=[],
            confidence=0.0,
            model="Error"
        )

# --- NEW DEDICATED ENDPOINT ---
@app.post("/summarize/{filename}")
@traceable(name="document_summary")
async def summarize_document(filename: str):
    """
    DETERMINISTIC SUMMARIZATION (Qdrant Version):
    Fetches all chunks for a file using Scroll, sorts them by chunk_id,
    and applies the "Bookend Strategy" (Intro + Body + Outro).
    """
    print(f"📑 Generating Summary for: {filename}")
    
    try:
        # 1. Fetch ALL chunks for this file using Qdrant Scroll
        # Qdrant's scroll API is used to iterate over points
        scroll_filter = Filter(
            must=[
                FieldCondition(
                    key="source", 
                    match=MatchValue(value=filename)
                )
            ]
        )
        
        all_points = []
        next_offset = None
        
        # Loop to get every single chunk (if > batch size)
        while True:
            records, next_offset = vector_db.client.scroll(
                collection_name=vector_db.collection_name,
                scroll_filter=scroll_filter,
                limit=100,
                offset=next_offset,
                with_payload=True,
                with_vectors=False
            )
            all_points.extend(records)
            if next_offset is None:
                break
                
        if not all_points:
             return {"summary": "Document not found in memory."}

        # 2. Extract and Sort Chunks
        # We need to sort by 'chunk_id' to read the doc in order
        docs_with_meta = []
        for record in all_points:
            payload = record.payload
            text = payload.get("text", "")
            chunk_id = int(payload.get("chunk_id", 0))
            docs_with_meta.append((chunk_id, text, payload))
            
        # Sort by chunk_id
        sorted_chunks = sorted(docs_with_meta, key=lambda x: x[0])
        total_chunks = len(sorted_chunks)

        # 3. Select Representative Chunks (Bookend Strategy)
        if total_chunks <= 10:
            selected_indices = range(total_chunks)
        else:
            indices = [0, 1, 2] # Intro
            indices += [total_chunks - 1, total_chunks - 2] # Outro
            step = total_chunks // 4
            indices += [step, step*2, step*3] # Middle
            selected_indices = sorted(list(set(indices)))

        # 4. Build Context
        context_text = ""
        for idx in selected_indices:
            if idx < total_chunks:
                _, doc, meta = sorted_chunks[idx]
                context_text += f"\n[Section: {meta.get('section', 'Body')} | Page {meta.get('page', '?')}]\n{doc}\n"

        # 5. Generate Summary
        system_prompt = """
        You are a Senior Executive Assistant.
        Summarize the provided document structure into a concise Executive Brief.
        
        FORMAT:
        1. **Executive Overview**: One paragraph summary.
        2. **Key Financials/Facts**: Bullet points of important numbers.
        3. **Strategic Highlights**: Important decisions or risks.
        """
        
        summary = await asyncio.to_thread(
            agent.llm.generate, 
            prompt="Generate the Executive Brief.", 
            system_prompt=f"{system_prompt}\n\n--- DOCUMENT CONTENT ---\n{context_text}"
        )
        return {"summary": summary}

    except Exception as e:
        return {"summary": f"Summary Error: {str(e)}"}