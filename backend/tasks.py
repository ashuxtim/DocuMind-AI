import os
import asyncio
import redis
from celery.exceptions import Ignore
from celery_app import celery_app
from state_manager import state_manager
from ingest import DocuMindIngest

# 🔴 FIX: Environment-driven Redis URL for Docker/Kubernetes compatibility
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# decode_responses=False is often safer for distributed locks depending on the redis-py version, 
# but we will rely on standard instantiation here.
redis_client = redis.Redis.from_url(REDIS_URL)

@celery_app.task(bind=True, name="ingest_document")
def ingest_document_task(self, file_path: str, filename: str):
    """
    Celery task wrapper for document ingestion.
    Implements distributed GPU locking, cooperative cancellation, and state sync.
    """
    # 1. Update state to PROCESSING
    self.update_state(state='PROCESSING', meta={'progress': 0, 'status': 'Waiting for GPU...'})
    state_manager.set_processing(filename, self.request.id)

    # 2. Cooperative Cancellation Token
    def check_if_cancelled():
        status_data = state_manager.get_status(filename)
        return status_data is not None and status_data.get("status") == "cancelled"

    # 3. Configure the Distributed GPU Lock
    # timeout=1800 (30 mins): Ensures heavy PDFs don't lose the lock mid-process
    # blocking_timeout=600 (10 mins): Allows workers to queue up gracefully rather than crashing
    lock_name = "documind_gpu_lock"
    gpu_lock = redis_client.lock(
        lock_name,
        timeout=1800,
        blocking=True,
        blocking_timeout=600
    )

    try:
        # 4. Acquire the Lock BEFORE initializing heavy GPU/LLM components
        acquired = gpu_lock.acquire()
        if not acquired:
            raise RuntimeError("GPU lock acquisition timed out. Workers are heavily backlogged.")

        self.update_state(state='PROCESSING', meta={'progress': 5, 'status': 'GPU Acquired. Starting ingestion...'})
        
        # 🔴 FIX: Instantiate AFTER lock to protect GPU memory
        ingestor = DocuMindIngest()

        # 5. Hardened Async Execution Block
        result = asyncio.run(
            ingestor.process_document(
                file_path=file_path,
                filename=filename,
                cancellation_token=check_if_cancelled
            )
        )

        # 6. Translate legacy string returns into proper exceptions defensively
        if isinstance(result, str):
            if result == "cancelled":
                raise asyncio.CancelledError("Task was cancelled by user via API.")
            if result.startswith("Parsing failed") or result == "empty_file":
                raise ValueError(f"Document parsing failed: {result}")

        # 7. SUCCESS STATE (Redis updated before Celery)
        state_manager.set_completed(filename)
        self.update_state(state='SUCCESS', meta={'status': 'Completed', 'filename': filename})
        return {"status": "completed", "filename": filename}

    except asyncio.CancelledError:
        # 8. CANCELLED STATE (Clean Revocation)
        print(f"🚫 Task intentionally aborted for {filename}")
        state_manager.set_cancelled(filename)
        self.update_state(state='REVOKED', meta={'status': 'Cancelled by user'})
        raise Ignore()

    except Exception as e:
        # 9. FAILED STATE
        error_msg = str(e)
        print(f"❌ Task failed for {filename}: {error_msg}")
        state_manager.set_failed(filename, error_msg)
        self.update_state(state='FAILURE', meta={'error': error_msg})
        raise

    finally:
        # 10. CRASH-SAFE LOCK RELEASE
        # Guaranteed to release the GPU whether we succeed, fail, or get cancelled
        try:
            # Check if this specific worker still owns the lock before releasing
            if gpu_lock.locked() and gpu_lock.owned():
                gpu_lock.release()
                print(f"🔓 GPU lock released for {filename}")
        except Exception as e:
            print(f"⚠️ Failed to gracefully release GPU lock for {filename}: {e}")