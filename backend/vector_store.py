import os
import hashlib
from typing import List, Dict, Optional, Any
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, MatchAny,
    PayloadSchemaType
)
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings

# Qdrant upsert batch size — kept conservative to avoid timeouts on large documents
UPSERT_BATCH_SIZE = 100


class VectorStore:
    def __init__(self, collection_name: str = "documind_docs"):
        host = os.getenv("QDRANT_HOST", "localhost")
        port = int(os.getenv("QDRANT_PORT", 6333))

        print(f"🔌 Connecting to Vector DB at {host}:{port}...")

        # gRPC transport (2-3x throughput on upsert/search)
        self.client = QdrantClient(
            host=host,
            port=port,
            grpc_port=int(os.getenv("QDRANT_GRPC_PORT", 6334)),
            prefer_grpc=True
        )
        self.collection_name = collection_name

        # NVIDIA NIM embeddings — replaces local SentenceTransformer (BGE)
        # Model: llama-nemotron-embed-1b-v2 — 2048-dim, 8192-token context, commercial use
        # LangChain client batches embed_documents() at 50 passages/request internally.
        # ingest.py sends batches of 20, so every call fits within one API request.
        # Vectors are L2-normalised by the API — normalize_embeddings is not a caller concern.
        self.embedding_model = NVIDIAEmbeddings(
            model=os.getenv("EMBED_MODEL", "nvidia/nv-embedqa-mistral-7b-v2"),
            api_key=os.getenv("NVIDIA_API_KEY"),
            truncate="END"
        )
        self.vector_size = int(os.getenv("EMBED_DIM", "4096"))

        try:
            self._ensure_collection()
        except Exception as e:
            print(f"⚠️ Qdrant not available yet ({e}). Collection will be created on first use.")

    def _ensure_collection(self):
        collections = self.client.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)

        if not exists:
            print(f"🧠 Creating Qdrant collection: {self.collection_name}")

            # payload indexes + on_disk to save RAM
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,
                    on_disk=True    # vectors stored on disk, not in RAM
                )
            )

            # payload indexes for fast filtered search and deletion
            self._create_payload_indexes()

        else:
            # Backfill indexes on existing collections.
            # Safe to call even if index already exists — Qdrant ignores duplicates.
            print(f"🔍 Collection exists — verifying payload indexes...")
            self._create_payload_indexes()

            # Warn if existing collection has wrong vector size (e.g. old 768-dim BGE)
            info = self.client.get_collection(self.collection_name)
            existing_size = info.config.params.vectors.size
            if existing_size != self.vector_size:
                print(f"⚠️  VECTOR SIZE MISMATCH: collection has {existing_size}-dim vectors "
                      f"but model produces {self.vector_size}-dim. "
                      f"Run `make wipe-qdrant` and re-ingest all documents.")

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
                # Qdrant raises if index already exists — that is expected and safe to ignore.
                # Any other error is a real failure and must be visible.
                if "already exists" in str(e).lower():
                    print(f"   ℹ️  Payload index already exists: {field_name}")
                else:
                    raise RuntimeError(f"Failed to create payload index '{field_name}': {e}") from e

    # Deterministic ID from filename + full text content.
    # Deliberately excludes chunk_idx — ingest.py calls add_documents one chunk at a time
    # so idx always resets to 0. Full text hash is collision-safe and position-independent.
    def _make_point_id(self, filename: str, text: str) -> str:
        raw = f"{filename}::{text}"
        return hashlib.md5(raw.encode()).hexdigest()

    def add_documents(self, texts: List[str], metadatas: List[Dict], filename: str):
        if not texts:
            return

        # NVIDIAEmbeddings.embed_documents() handles batching internally (max 50/request).
        # ingest.py sends batches of 20 — always within one API request.
        # Returns L2-normalised vectors — no post-processing needed.
        embeddings = self.embedding_model.embed_documents(texts)

        points = [
            PointStruct(
                id=self._make_point_id(filename, text),
                vector=emb,
                payload={**meta, "text": text, "source": filename}
            )
            for i, (text, meta, emb) in enumerate(zip(texts, metadatas, embeddings))
        ]

        # Batch upsert to Qdrant — avoids timeouts on large documents
        num_batches = -(-len(points) // UPSERT_BATCH_SIZE)  # ceiling division
        for i in range(0, len(points), UPSERT_BATCH_SIZE):
            batch = points[i : i + UPSERT_BATCH_SIZE]
            self.client.upsert(collection_name=self.collection_name, points=batch)

        print(f"   -> Indexed {len(points)} chunks in {num_batches} batch(es).")

    def search(self, query: str, limit: int = 15, filters: Dict[str, Any] = None) -> List[Dict]:
        # embed_query() handles the query/passage asymmetry internally.
        # BGE instruction prefix removed — it was BGE-specific and does not apply here.
        query_vector = self.embedding_model.embed_query(query)

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

        # score_threshold drops clearly irrelevant results before reranking.
        # Default 0.30 is a starting point — tune via AGENT_MIN_VECTOR_SCORE after re-ingest.
        # Both thresholds (vector + reranker) are env-var controlled for production tuning.
        min_score = float(os.getenv("AGENT_MIN_VECTOR_SCORE", "0.30"))
        search_result = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            score_threshold=min_score
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
        # source field is indexed — this is O(log n) not O(n)
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
