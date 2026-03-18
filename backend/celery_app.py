import os
from celery import Celery
from celery.signals import worker_process_init

# Fail loudly if Redis is not configured — no silent localhost fallback
REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise EnvironmentError("REDIS_URL environment variable is not set")

celery_app = Celery(
    "documind_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    result_expires=3600,   # 1 hour — covers any realistic frontend polling window
)

# Register tasks
import tasks  # noqa: E402, F401


@worker_process_init.connect
def init_worker_resources(**kwargs):
    """
    Runs once per Celery worker process after fork.
    Creates all shared singletons exactly once per worker.
    """
    import sys
    sys.path.insert(0, '/app')
    
    import asyncio
    import tasks as _tasks
    from state_manager import StateManager
    from ingest import DocuMindIngest
    from minio_storage import MinIOStorage

    _tasks.state_manager = StateManager()
    _tasks._ingestor      = DocuMindIngest()
    _tasks._minio         = MinIOStorage()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _tasks._event_loop = loop

    print(f"✅ Worker PID {os.getpid()} initialised — all connections established")