import os
import asyncio
import redis
from typing import List, Dict
from vector_store import VectorStore
from parser import SmartPDFParser
from graph_agent import get_graph_builder
from knowledge_graph import KnowledgeBase

CLOUD_PROVIDERS = {"vllm", "openai", "gemini", "groq", "anthropic", "cohere", "nvidia"}


class DocuMindIngest:
    def __init__(self):
        self.vector_db = VectorStore()
        self.parser = SmartPDFParser()
        self.agent = get_graph_builder()
        self.kb = KnowledgeBase()

        self.provider = os.getenv("LLM_PROVIDER", "ollama").lower()
        self.is_cloud = self.provider in CLOUD_PROVIDERS
        self.concurrency = 5 if self.is_cloud else 1

        # One Redis client for the lifetime of this ingestor
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        self.redis_client = redis.Redis.from_url(redis_url)

        # Global semaphore — controls concurrency across all documents
        self.semaphore = asyncio.Semaphore(self.concurrency)

        print(f"⚙️ Ingestion Mode: {self.provider.upper()} | Cloud: {self.is_cloud} | Concurrency: {self.concurrency}x")

    async def cleanup(self, filename: str):
        """Wipes all traces of a file from all stores."""
        print(f"🧹 CLEANUP PROTOCOL INITIATED for {filename}")
        try:
            self.vector_db.delete_file(filename)
            print("   - Vector entries deleted")
        except Exception as e:
            print(f"   - Vector delete warning: {e}")

        try:
            self.kb.delete_document(filename)
            print("   - Graph entries deleted")
        except Exception as e:
            print(f"   - Graph delete warning: {e}")

    async def _call_with_retry(self, fn, *args, max_retries: int = 3, base_delay: float = 2.0):
        """
        Retry a blocking call wrapped in asyncio.to_thread with exponential backoff.
        Handles rate limits and transient errors.
        """
        for attempt in range(max_retries):
            try:
                return await asyncio.to_thread(fn, *args)
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = "429" in err_str or "rate limit" in err_str or "quota" in err_str
                is_last = attempt == max_retries - 1

                if is_last:
                    raise

                delay = base_delay * (2 ** attempt)
                if is_rate_limit:
                    print(f"   ⏳ Rate limit — retrying in {delay:.0f}s ({attempt+2}/{max_retries})...")
                else:
                    print(f"   ⚠️ LLM error attempt {attempt+1} — retrying in {delay:.0f}s: {e}")

                await asyncio.sleep(delay)
        
    async def process_document(self, file_path: str, filename: str, cancellation_token):
        """Orchestrates ingestion: Dedup -> Parse -> Vector (batch) -> Graph (concurrent)"""
        print(f"🚀 Processing: {filename}")

        try:
            # Dedup — always wipe prior data for clean re-ingest
            await self.cleanup(filename)

            # Parse — offloaded to thread so event loop stays free
            chunks = await asyncio.to_thread(self.parser.parse_with_metadata, file_path)
            print(f"   - Parsed {len(chunks)} chunks (Smart Layout)")

            if not chunks:
                return "empty_file"

            if cancellation_token():
                return "cancelled"

            # ── Phase A: Batch vector insert ──────────────────────────────────
            batch_size = 20
            vector_errors = 0
            for batch_start in range(0, len(chunks), batch_size):
                batch = chunks[batch_start:batch_start + batch_size]
                texts = [c["text"] for c in batch]
                metadatas = [{**c["metadata"], "source": filename} for c in batch]
                try:
                    self.vector_db.add_documents(
                        texts=texts,
                        metadatas=metadatas,
                        filename=filename
                    )
                except Exception as e:
                    print(f"   ⚠️ Vector batch error at chunk {batch_start}: {e}")
                    vector_errors += 1

            if vector_errors:
                print(f"   ⚠️ {vector_errors} vector batch(es) failed — partial index")

            print(f"   ✅ Vector insert complete ({len(chunks)} chunks, {vector_errors} errors)")

            if cancellation_token():
                await self.cleanup(filename)
                return "cancelled"

            # ── Phase B: Graph extraction (concurrent, LLM-driven) ────────────
            all_graphs = []

            async def extract_graph_safe(i, chunk):
                async with self.semaphore:
                    if cancellation_token():
                        return
                    await self._extract_graph_for_chunk(i, chunk, filename,
                                                        cancellation_token, all_graphs)

            tasks = [extract_graph_safe(i, chunk) for i, chunk in enumerate(chunks)]
            await asyncio.gather(*tasks)

            if cancellation_token():
                await self.cleanup(filename)
                return "cancelled"

            # ── Phase C: Entity registry + bulk graph write ───────────────────
            if all_graphs:
                try:
                    all_graphs = self.agent.apply_entity_registry(all_graphs)
                    self.kb.ingest_graph(all_graphs, filename)
                except Exception as e:
                    print(f"   ⚠️ Graph bulk write failed for {filename}: {e}")
                    print(f"   ℹ️ Vectors indexed successfully. Re-ingest to rebuild graph.")

            status = "completed_partial" if vector_errors else "completed"
            print(f"✅ Finished {filename}! Status: {status}")
            return status

        except Exception as e:
            print(f"   ❌ Fatal error for {filename}: {e}")
            await self.cleanup(filename)
            return f"failed: {e}"

    async def _extract_graph_for_chunk(self, i: int, chunk: Dict, filename: str,
                                        cancellation_token, all_graphs: List):
        text = chunk["text"]
        metadata = chunk["metadata"]
        page_num = metadata.get("page", 1)
        chunk_id = f"{filename}::chunk_{i}::page_{page_num}"

        try:
            if self.is_cloud:
                graph = await self._call_with_retry(
                    self.agent.extract_relationships, text, chunk_id, filename
                )
            else:
                r_lock = self.redis_client.lock("ollama_inference_lock", timeout=300)
                print(f"   ⏳ Chunk {i} waiting for Ollama availability...")

                graph = {"nodes": [], "edges": []}
                acquired = await asyncio.to_thread(r_lock.acquire, blocking=True, blocking_timeout=290)

                if not acquired:
                    print(f"   ⚠️ Chunk {i}: lock timeout — skipping graph extraction")
                    return

                try:
                    if not cancellation_token():
                        graph = await self._call_with_retry(
                            self.agent.extract_relationships, text, chunk_id, filename
                        )
                finally:
                    if r_lock.owned():
                        r_lock.release()

            if graph.get("nodes"):
                all_graphs.append(graph)

        except Exception as e:
            print(f"      ⚠️ Chunk {i} Graph error: {e}")