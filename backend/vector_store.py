import os
import re
import hashlib
import mmh3
from collections import Counter
from typing import List, Dict, Optional, Any
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, SparseVectorParams, Modifier,
    PointStruct, SparseVector,
    Filter, FieldCondition, MatchValue, MatchAny,
    PayloadSchemaType, Prefetch, FusionQuery, Fusion
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
            print(f"🧠 Creating Qdrant collection: {self.collection_name} (named vectors: dense + bm25)")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "dense": VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE,
                        on_disk=True
                    )
                },
                sparse_vectors_config={
                    "bm25": SparseVectorParams(modifier=Modifier.IDF)
                }
            )
            self._create_payload_indexes()

        else:
            # Backfill indexes on existing collections.
            # Safe to call even if index already exists — Qdrant ignores duplicates.
            print(f"🔍 Collection exists — verifying payload indexes...")
            self._create_payload_indexes()

            info = self.client.get_collection(self.collection_name)
            vectors_config = info.config.params.vectors
            if isinstance(vectors_config, dict):
                dense_cfg = vectors_config.get("dense")
                if dense_cfg and dense_cfg.size != self.vector_size:
                    print(f"⚠️  VECTOR SIZE MISMATCH: 'dense' slot has {dense_cfg.size}-dim "
                          f"but model produces {self.vector_size}-dim. "
                          f"Run `make wipe-qdrant` and re-ingest all documents.")
                if "bm25" not in (info.config.params.sparse_vectors or {}):
                    raise RuntimeError(
                        "Collection has named dense vectors but no 'bm25' sparse slot. "
                        "Run `make wipe-qdrant` and re-ingest."
                    )
            else:
                raise RuntimeError(
                    f"Collection '{self.collection_name}' uses old flat VectorParams schema "
                    f"(size={vectors_config.size}). Cannot migrate in-place. "
                    f"Run `make wipe-qdrant` then re-ingest all documents."
                )

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

    def _compute_sparse_vector(self, text: str) -> SparseVector:
        # Tokenize → TF count → mmh3 hash each token to a 1M-slot index space.
        # Client sends raw TF; Modifier.IDF on the collection applies IDF server-side → BM25.
        tokens = re.findall(r'\b[a-zA-Z0-9]+\b', text.lower())
        term_counts = Counter(tokens)
        indices = [mmh3.hash(term, signed=False) % (2 ** 20) for term in term_counts]
        values  = [float(count) for count in term_counts.values()]
        return SparseVector(indices=indices, values=values)

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
                vector={
                    "dense": emb,
                    "bm25":  self._compute_sparse_vector(text),
                },
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

    def hybrid_search(self, query: str, limit: int = 15, filters: Dict[str, Any] = None) -> List[Dict]:
        dense_query_vector  = self.embedding_model.embed_query(query)
        sparse_query_vector = self._compute_sparse_vector(query)

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

        # No score_threshold on Prefetch — BM25 dot-product scores and cosine scores
        # are on different scales. Thresholding happens after reranking in agent_graph.py.
        search_result = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[
                Prefetch(
                    query=dense_query_vector,
                    using="dense",
                    filter=query_filter,
                    limit=limit * 3,
                ),
                Prefetch(
                    query=sparse_query_vector,
                    using="bm25",
                    filter=query_filter,
                    limit=limit * 3,
                ),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=limit,
            with_payload=True,
        ).points

        return [
            {
                "text": hit.payload.get("text", ""),
                "metadata": {k: v for k, v in hit.payload.items() if k != "text"},
                "score": hit.score,
            }
            for hit in search_result
        ]

    def search(self, query: str, limit: int = 15, filters: Dict[str, Any] = None) -> List[Dict]:
        # Backward-compat alias — all calls now go through hybrid_search().
        return self.hybrid_search(query=query, limit=limit, filters=filters)

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
