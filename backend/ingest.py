import os
import networkx as nx
import asyncio
import redis
from datetime import datetime
from vector_store import VectorStore 
from parser import SmartPDFParser
from graph_agent import GraphBuilder
from knowledge_graph import KnowledgeBase

class DocuMindIngest:
    def __init__(self):
        # 1. NEW VECTOR DB (Qdrant)
        # This wrapper handles the connection and collection creation automatically
        self.vector_db = VectorStore()
        
        # 2. Initialize Components
        self.parser = SmartPDFParser()
        self.agent = GraphBuilder()
        self.kb = KnowledgeBase()

        # 3. Auto-Detect Concurrency
        self.provider = os.getenv("LLM_PROVIDER", "ollama").lower()
        
        # Cloud (vLLM/OpenAI/Gemini) = Parallel Processing allowed
        # Local (Ollama) = Serial Processing to save CPU
        self.is_cloud = self.provider in ["vllm", "openai", "gemini"]
        self.concurrency = 5 if self.is_cloud else 1
        
        print(f"⚙️ Ingestion Mode: {self.provider.upper()} | Concurrency: {self.concurrency}x")

    async def cleanup(self, filename: str):
        """Wipes all traces of a file if cancelled/deleted."""
        print(f"🧹 CLEANUP PROTOCOL INITIATED for {filename}")
        try:
            # NEW: Qdrant Delete
            self.vector_db.delete_file(filename)
            print("   - Vector entries deleted")
        except Exception as e: 
            print(f"   - Vector delete warning: {e}")
            
        try:
            self.kb.delete_document(filename)
            print("   - Graph entries deleted")
        except Exception as e:
            print(f"   - Graph delete warning: {e}")

    async def process_document(self, file_path: str, filename: str, cancellation_token):
        """Orchestrates ingestion: Parse -> Vector -> Graph"""
        print(f"🚀 Processing: {filename}")
        
        # PHASE 3.1: Parsing with Layout Awareness
        try:
            chunks = self.parser.parse_with_metadata(file_path)
            print(f"   - Parsed {len(chunks)} chunks (Smart Layout)")
        except Exception as e:
            return f"Parsing failed: {e}"

        if not chunks:
            return "empty_file"

        # Semaphore limits concurrency
        semaphore = asyncio.Semaphore(self.concurrency)

        async def process_chunk_safe(i, chunk):
            async with semaphore:
                if cancellation_token(): return
                await self._process_single_chunk(i, chunk, filename, cancellation_token)

        # Launch tasks
        tasks = [process_chunk_safe(i, chunk) for i, chunk in enumerate(chunks)]
        await asyncio.gather(*tasks)

        if cancellation_token(): 
            await self.cleanup(filename)
            return "cancelled"

        print(f"✅ Finished {filename}!")
        return "completed"

    async def _process_single_chunk(self, i, chunk, filename, cancellation_token):
        text = chunk["text"]
        metadata = chunk["metadata"]
        metadata["source"] = filename
        
        # Extract metadata for Graph
        page_num = metadata.get("page", 1)

        # A. Vector Add (NEW QDRANT LOGIC)
        try:
            # We insert this chunk immediately. 
            # Note: The VectorStore wrapper handles the embedding generation.
            self.vector_db.add_documents(
                texts=[text], 
                metadatas=[metadata], 
                filename=filename
            )
        except Exception as e:
            print(f"   - Vector Error chunk {i}: {e}")
        
        # B. Graph Extraction
        if cancellation_token(): return

        try:
            relations = []

            # Use Async Threading for LLM Call
            if self.is_cloud:
                # No Lock needed for Cloud APIs
                relations = await asyncio.to_thread(self.agent.extract_relationships, text)
            else:
                # Redis Lock needed for Local Ollama
                # 🔴 FIX: USE ENVIRONMENT VARIABLE FOR REDIS
                redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0") 
                redis_client = redis.Redis.from_url(redis_url)
                # 🔴 FIX: Remove blocking_timeout. Force the thread to wait its turn.
                # This guarantees 100% graph extraction coverage, even if it takes longer.
                r_lock = redis_client.lock("gpu_inference_lock", timeout=300)
                
                print(f"   ⏳ Chunk {i} waiting for GPU availability...")
                
                # Blocking=True without a timeout will wait indefinitely until the lock is freed
                if r_lock.acquire(blocking=True):
                    try:
                        if not cancellation_token():
                            relations = await asyncio.to_thread(self.agent.extract_relationships, text)
                    finally:
                        r_lock.release()

            # PHASE 2.1: Persist to Neo4j with Rich Metadata
            if relations:
                self.kb.add_relations(
                    relations, 
                    source_file=filename,
                    page_number=page_num
                )
                
        except Exception as e:
            print(f"      ⚠️ Chunk {i} Graph error: {e}")