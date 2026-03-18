import os
import redis
from datetime import datetime
from typing import Optional, Dict

# ── TTL constants ─────────────────────────────────────────────────────────────
TTL_PROCESSING = 7  * 24 * 3600   # 7 days
TTL_COMPLETED  = 30 * 24 * 3600   # 30 days
TTL_FAILED     = 7  * 24 * 3600   # 7 days
TTL_CANCELLED  = 2  * 24 * 3600   # 2 days


class StateManager:
    """
    Manages document ingestion state in Redis.
    Tracks: filename -> {task_id, status, timestamps, error}
    """

    def __init__(self):
        self._redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._client = None
        self._connect()

    def _connect(self):
        """Attempt connection. Sets self._client=None on failure."""
        try:
            client = redis.Redis.from_url(self._redis_url, decode_responses=True)
            client.ping()
            self._client = client
            print("✅ StateManager connected to Redis")
        except Exception as e:
            print(f"⚠️ Redis not available at startup: {e}. Will retry on first use.")
            self._client = None

    @property
    def redis_client(self):
        """Lazy reconnect — try to (re)connect if client is None."""
        if self._client is None:
            self._connect()
        return self._client

    def _get_key(self, filename: str) -> str:
        return f"documind:file_status:{filename}"

    def _ttl_for_status(self, status: str) -> int:
        return {
            "processing": TTL_PROCESSING,
            "completed":  TTL_COMPLETED,
            "failed":     TTL_FAILED,
            "cancelled":  TTL_CANCELLED,
        }.get(status, TTL_COMPLETED)

    def _normalise(self, data: dict) -> dict:
        """Convert empty strings to None for consistency."""
        if data.get("completed_at") == "":
            data["completed_at"] = None
        if data.get("error") == "":
            data["error"] = None
        return data

    def set_processing(self, filename: str, task_id: str):
        if not self.redis_client:
            return
        key = self._get_key(filename)
        with self.redis_client.pipeline() as pipe:
            pipe.hset(key, mapping={
                "task_id":      task_id,
                "status":       "processing",
                "uploaded_at":  datetime.utcnow().isoformat(),
                "completed_at": "",
                "error":        ""
            })
            pipe.expire(key, TTL_PROCESSING)
            pipe.execute()
        print(f"📝 State: {filename} → processing (task: {task_id})")

    def set_completed(self, filename: str):
        if not self.redis_client:
            return
        key = self._get_key(filename)
        with self.redis_client.pipeline() as pipe:
            pipe.hset(key, mapping={
                "status":       "completed",
                "completed_at": datetime.utcnow().isoformat(),
            })
            pipe.expire(key, TTL_COMPLETED)
            pipe.execute()
        print(f"✅ State: {filename} → completed")

    def set_failed(self, filename: str, error: str):
        if not self.redis_client:
            return
        key = self._get_key(filename)
        with self.redis_client.pipeline() as pipe:
            pipe.hset(key, mapping={
                "status":       "failed",
                "completed_at": datetime.utcnow().isoformat(),
                "error":        error[:500],
            })
            pipe.expire(key, TTL_FAILED)
            pipe.execute()
        print(f"❌ State: {filename} → failed ({error[:100]})")

    def set_cancelled(self, filename: str):
        if not self.redis_client:
            return
        key = self._get_key(filename)
        with self.redis_client.pipeline() as pipe:
            pipe.hset(key, mapping={
                "status":       "cancelled",
                "completed_at": datetime.utcnow().isoformat(),
            })
            pipe.expire(key, TTL_CANCELLED)
            pipe.execute()
        print(f"🚫 State: {filename} → cancelled")

    def get_status(self, filename: str) -> Optional[Dict]:
        if not self.redis_client:
            return None
        key = self._get_key(filename)
        data = self.redis_client.hgetall(key)
        if not data:
            return None
        return self._normalise(data)

    def get_all_statuses(self) -> Dict[str, Dict]:
        """Get status for all files using non-blocking SCAN."""
        if not self.redis_client:
            return {}
        pattern = "documind:file_status:*"
        statuses = {}
        cursor = 0
        while True:
            cursor, keys = self.redis_client.scan(
                cursor=cursor, match=pattern, count=100
            )
            for key in keys:
                filename = key.replace("documind:file_status:", "")
                data = self.redis_client.hgetall(key)
                statuses[filename] = self._normalise(data)
            if cursor == 0:
                break
        return statuses

    def delete_task(self, filename: str):
        if not self.redis_client:
            return
        key = self._get_key(filename)
        self.redis_client.delete(key)
        print(f"🗑️ State: {filename} → deleted")

    def clear_document_state(self, filename: str):
        """
        Delete all Redis keys associated with a document.
        Uses scan_iter — non-blocking, consistent with get_all_statuses pattern.
        Called by /delete endpoint instead of direct redis_client access.
        """
        if not self.redis_client:
            return
        keys = list(self.redis_client.scan_iter(f"*:{filename}*"))
        if keys:
            self.redis_client.delete(*keys)
        print(f"🗑️ State: {filename} → all keys cleared")

    def invalidate_cache(self, key: str):
        """
        Invalidate a named cache key.
        Single encapsulated path for all cache invalidation — no direct
        redis_client.delete() calls outside StateManager.
        """
        if not self.redis_client:
            return
        try:
            self.redis_client.delete(key)
        except Exception as e:
            print(f"⚠️ Cache invalidation failed for '{key}': {e}")


# Module-level instance removed — initialised via worker_process_init
# in celery_app.py for workers, and via lifespan in main.py for FastAPI