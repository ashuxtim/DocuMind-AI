import os
import asyncio
from datetime import datetime
from typing import Optional
import redis
from celery.exceptions import Ignore
from celery_app import celery_app

# ── Module-level singletons ───────────────────────────────────────────────────
# Populated by worker_process_init signal in celery_app.py.
# None until worker process initialises — never instantiated at import time.
state_manager = None
_ingestor      = None
_minio         = None
_event_loop    = None

REDIS_URL   = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

CLOUD_PROVIDERS = {"vllm", "openai", "gemini", "groq", "anthropic", "cohere", "nvidia"}


def _run_async(coro):
    """
    Safely run an async coroutine from sync Celery context.
    Reuses the persistent per-worker event loop set in worker_process_init.
    Falls back to asyncio.run() if no loop is available (e.g. test context).
    """
    global _event_loop
    if _event_loop is not None and not _event_loop.is_closed():
        return _event_loop.run_until_complete(coro)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@celery_app.task(bind=True, name="ingest_document")
def ingest_document_task(self, filename: str):
    """
    Celery task wrapper for document ingestion.
    GPU lock is conditional — only acquired for local providers (Ollama, vLLM).
    Cloud providers (Groq, NVIDIA, OpenAI) skip the lock entirely.
    """
    # Guard — ensure worker_process_init has fired before using singletons
    if state_manager is None or _ingestor is None or _minio is None:
        raise RuntimeError("Worker not initialised — worker_process_init signal may not have fired.")

    self.update_state(state='PROCESSING', meta={'progress': 0, 'status': 'Starting ingestion...'})
    state_manager.set_processing(filename, self.request.id)

    def check_if_cancelled():
        status_data = state_manager.get_status(filename)
        return status_data is not None and status_data.get("status") == "cancelled"

    # Determine if GPU lock is needed
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    needs_lock = provider not in CLOUD_PROVIDERS

    gpu_lock = None
    if needs_lock:
        gpu_lock = redis_client.lock(
            "ollama_inference_lock",
            timeout=1800,
            blocking=True,
            blocking_timeout=600
        )

    try:
        # Acquire lock only for local providers
        if needs_lock:
            acquired = gpu_lock.acquire()
            if not acquired:
                raise RuntimeError("GPU lock acquisition timed out — workers heavily backlogged.")
            self.update_state(state='PROCESSING', meta={'progress': 5, 'status': 'Lock acquired. Starting...'})
        else:
            self.update_state(state='PROCESSING', meta={'progress': 5, 'status': 'Ingesting...'})

        # Surgical fix — context manager guarantees temp file cleanup even if
        # process_document raises.  Replaces download_to_temp + finally block.
        with _minio.temp_download(filename) as file_path:
            result = _run_async(
                _ingestor.process_document(
                    file_path=file_path,
                    filename=filename,
                    cancellation_token=check_if_cancelled
                )
            )

            if isinstance(result, str):
                if result == "cancelled":
                    raise asyncio.CancelledError("Cancelled by user.")
                if result.startswith("Parsing failed") or result == "empty_file":
                    raise ValueError(f"Document parsing failed: {result}")

        # Single source of truth — StateManager handles its own reconnect
        state_manager.set_completed(filename)
        state_manager.invalidate_cache("cache:dashboard_graph")  # ← add this line
        self.update_state(state='SUCCESS', meta={'status': 'Completed', 'filename': filename})
        return {"status": "completed", "filename": filename}

    except asyncio.CancelledError:
        state_manager.set_cancelled(filename)
        self.update_state(state='REVOKED', meta={'status': 'Cancelled by user'})
        raise Ignore()

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Task failed for {filename}: {error_msg}")
        state_manager.set_failed(filename, error_msg)
        self.update_state(state='FAILURE', meta={'error': error_msg})
        raise

    finally:
        # Lock release — only if lock was acquired
        if needs_lock and gpu_lock is not None:
            try:
                if gpu_lock.owned():
                    gpu_lock.release()
                    print(f"🔓 GPU lock released for {filename}")
            except Exception as e:
                print(f"⚠️ Failed to release GPU lock for {filename}: {e}")