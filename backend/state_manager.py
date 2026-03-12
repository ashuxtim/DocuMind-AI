import os
import json
import redis
from datetime import datetime
from typing import Optional, Dict, List

class StateManager:
    """
    Manages document ingestion state in Redis.
    Tracks: filename -> {task_id, status, timestamps, error}
    """
    
    def __init__(self):
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            self.redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
            self.redis_client.ping()
            print("✅ StateManager connected to Redis")
        except Exception as e:
            print(f"❌ Redis connection failed: {e}")
            self.redis_client = None
    
    def _get_key(self, filename: str) -> str:
        """Generate Redis key for a filename"""
        return f"documind:file_status:{filename}"
    
    def set_processing(self, filename: str, task_id: str):
        """Mark file as processing"""
        if not self.redis_client:
            return
        
        data = {
            "task_id": task_id,
            "status": "processing",
            "uploaded_at": datetime.utcnow().isoformat(),
            "completed_at": "",
            "error": ""
        }
        
        key = self._get_key(filename)
        self.redis_client.hmset(key, data)
        self.redis_client.expire(key, 86400)
        print(f"📝 State: {filename} → processing (task: {task_id})")
    
    def set_completed(self, filename: str):
        """Mark file as completed"""
        if not self.redis_client:
            return
        
        key = self._get_key(filename)
        self.redis_client.hset(key, "status", "completed")
        self.redis_client.hset(key, "completed_at", datetime.utcnow().isoformat())
        print(f"✅ State: {filename} → completed")
    
    def set_failed(self, filename: str, error: str):
        """Mark file as failed"""
        if not self.redis_client:
            return
        
        key = self._get_key(filename)
        self.redis_client.hset(key, "status", "failed")
        self.redis_client.hset(key, "completed_at", datetime.utcnow().isoformat())
        self.redis_client.hset(key, "error", error)
        print(f"❌ State: {filename} → failed ({error})")
    
    def set_cancelled(self, filename: str):
        """Mark file as cancelled"""
        if not self.redis_client:
            return
        
        key = self._get_key(filename)
        self.redis_client.hset(key, "status", "cancelled")
        self.redis_client.hset(key, "completed_at", datetime.utcnow().isoformat())
        print(f"🚫 State: {filename} → cancelled")
    
    def get_status(self, filename: str) -> Optional[Dict]:
        """Get status for a specific file"""
        if not self.redis_client:
            return None
        
        key = self._get_key(filename)
        data = self.redis_client.hgetall(key)
        
        if not data:
            return None
        
        # Convert empty strings back to None for consistency
        if data.get("completed_at") == "":
            data["completed_at"] = None
        if data.get("error") == "":
            data["error"] = None
        
        return data

    
    def get_all_statuses(self) -> Dict[str, Dict]:
        """Get status for all files"""
        if not self.redis_client:
            return {}
        
        pattern = "documind:file_status:*"
        keys = self.redis_client.keys(pattern)
        
        statuses = {}
        for key in keys:
            filename = key.replace("documind:file_status:", "")
            data = self.redis_client.hgetall(key)
            
            # Convert empty strings back to None for consistency
            if data.get("completed_at") == "":
                data["completed_at"] = None
            if data.get("error") == "":
                data["error"] = None
            
            statuses[filename] = data
        
        return statuses

    
    def delete_task(self, filename: str):
        """Remove status tracking for a file completely"""
        if not self.redis_client:
            return
        
        key = self._get_key(filename)
        self.redis_client.delete(key)
        print(f"🗑️ State: {filename} → deleted")

state_manager = StateManager()
