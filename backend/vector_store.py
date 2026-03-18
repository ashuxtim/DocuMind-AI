import os
import hashlib
from typing import List, Dict, Optional, Any
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, MatchAny,
    PayloadSchemaType
)
from sentence_transformers import SentenceTransformer

# Fix 6 — batch size constant
UPSERT_BATCH_SIZE = 100


class VectorStore:
    def __init__(self, collection_name: str = "documind_docs"):
        host = os.getenv("QDRANT_HOST", "localhost")
        port = int(os.getenv("QDRANT_PORT", 6333))

        print(f"🔌 Connecting to Vector DB at {host}:{port}...")

        # Fix 8 — gRPC transport (2-3x throughput on upsert/search)
        self.client = QdrantClient(
            host=host,
            port=port,
            grpc_port=int(os.getenv("QDRANT_GRPC_PORT", 6334)),
            prefer_grpc=True
        )
        self.collection_name = collection_name

        # Fix 5 — upgrade from all-MiniLM-L6-v2 to BGE base
        # Better retrieval on domain-specific text, explicit CPU for 16GB system
        self.embedding_model = SentenceTransformer(
            "BAAI/bge-base-en-v1.5",
            device="cpu"
        )
        self.vector_size = 768  # Fix 5 — updated from 384

        try:
            self._ensure_collection()
        except Exception as e:
            print(f"⚠️ Qdrant not available yet ({e}). Collection will be created on first use.")

    def _ensure_collection(self):
        collections = self.client.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)

        if not exists:
            print(f"🧠 Creating Qdrant collection: {self.collection_name}")

            # Fix 3 + Fix 4 — payload indexes + on_disk to save RAM
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,
                    on_disk=True    # Fix 4 — vectors stored on disk, not in RAM
                )
            )

            # Fix 3 — payload indexes for fast filtered search and deletion
            self._create_payload_indexes()

        else:
            # Fix 3 partial — backfill indexes on existing collections
            # Safe to call even if index already exists — Qdrant ignores duplicates
            print(f"🔍 Collection exists — verifying payload indexes...")
            self._create_payload_indexes()

            # Warn if existing collection has wrong vector size (e.g. old 384-dim)
            info = self.client.get_collection(self.collection_name)
            existing_size = info.config.params.vectors.size
            if existing_size != self.vector_size:
                print(f"⚠️  VECTOR SIZE MISMATCH: collection has {existing_size}-dim vectors "
                      f"but model produces {self.vector_size}-dim. "
                      f"Delete the collection and re-ingest all documents.")

    def _create_payload_indexes(self):
        index_fields = [
            ("source",   PayloadSchemaType.KEYWORD),
            ("page",     PayloadSchemaType.INTEGER),
            ("section",  PayloadSchemaType.KEYWORD),
            ("chunk_id", PayloadSchemaType.INTEGER),
        ]
        for field_name, field_type in index_fields:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=field_type
                )
                print(f"   ✅ Payload index ready: {field_name}")
            except Exception as e:
                # Qdrant raises if index already exists — that is expected and safe to ignore
                # Any other error is a real failure and must be visible
                if "already exists" in str(e).lower():
                    print(f"   ℹ️  Payload index already exists: {field_name}")
                else:
                    raise RuntimeError(f"Failed to create payload index '{field_name}': {e}") from e

    # Fix 2 — deterministic ID from filename + full text content
    # Deliberately excludes chunk_idx — ingest.py calls add_documents one chunk at a time
    # so idx always resets to 0. Full text hash is collision-safe and position-independent.
    def _make_point_id(self, filename: str, text: str) -> str:
        raw = f"{filename}::{text}"
        return hashlib.md5(raw.encode()).hexdigest()

    def add_documents(self, texts: List[str], metadatas: List[Dict], filename: str):
        if not texts:
            return

        # Fix 1 — normalize_embeddings=True for correct cosine similarity scores
        # Fix 6 — batch_size=32 for memory-efficient encoding, progress bar for large docs
        embeddings = self.embedding_model.encode(
            texts,
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=len(texts) > 50
        ).tolist()

        points = [
            PointStruct(
                id=self._make_point_id(filename, text),  # Fix 2
                vector=emb,
                payload={**meta, "text": text, "source": filename}
            )
            for i, (text, meta, emb) in enumerate(zip(texts, metadatas, embeddings))
        ]

        # Fix 6 — batch upsert, no timeouts on large documents
        num_batches = -(-len(points) // UPSERT_BATCH_SIZE)  # ceiling division
        for i in range(0, len(points), UPSERT_BATCH_SIZE):
            batch = points[i : i + UPSERT_BATCH_SIZE]
            self.client.upsert(collection_name=self.collection_name, points=batch)

        print(f"   -> Indexed {len(points)} chunks in {num_batches} batch(es).")

    def search(self, query: str, limit: int = 15, filters: Dict[str, Any] = None) -> List[Dict]:
        # Fix 5 — BGE query instruction prefix for best retrieval accuracy
        prefixed_query = f"Represent this sentence for searching relevant passages: {query}"

        # Fix 1 — normalize_embeddings=True, consistent with add_documents
        query_vector = self.embedding_model.encode(
            prefixed_query,
            normalize_embeddings=True
        ).tolist()

        query_filter = None
        if filters:
            conditions = []
            for key, value in filters.items():
                if isinstance(value, list):
                    conditions.append(FieldCondition(key=key, match=MatchAny(any=value)))
                else:
                    conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
            if conditions:
                query_filter = Filter(must=conditions)

        # Fix 7 — score_threshold drops irrelevant results before reranking
        search_result = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            score_threshold=0.30    # Fix 7 — tune after re-ingestion if needed
        ).points

        return [
            {
                "text": hit.payload.get("text", ""),
                "metadata": {k: v for k, v in hit.payload.items() if k != "text"},
                "score": hit.score
            }
            for hit in search_result
        ]

    def delete_file(self, filename: str):
        # Fix 3 — source field is now indexed, this is O(log n) not O(n)
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="source",
                        match=MatchValue(value=filename)
                    )
                ]
            )
        )
        print(f"   -> Removed vectors for {filename}")