import os
from typing import List, Dict, Optional, Any
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, MatchAny
from sentence_transformers import SentenceTransformer
import uuid

class VectorStore:
    def __init__(self, collection_name: str = "documind_docs"):
        # Read from .env, default to localhost if missing
        host = os.getenv("QDRANT_HOST", "localhost")
        port = int(os.getenv("QDRANT_PORT", 6333))
        
        print(f"🔌 Connecting to Vector DB at {host}:{port}...")
        self.client = QdrantClient(host=host, port=port)
        self.collection_name = collection_name
        
        # Load embedding model
        self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        self.vector_size = 384 

        self._ensure_collection()

    def _ensure_collection(self):
        """Creates the collection if it doesn't exist."""
        collections = self.client.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)
        
        if not exists:
            print(f"🧠 Creating Qdrant collection: {self.collection_name}")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE)
            )

    def add_documents(self, texts: List[str], metadatas: List[Dict], filename: str):
        """Generates embeddings and pushes to Qdrant."""
        if not texts: return

        # 1. Generate Embeddings
        embeddings = self.embedding_model.encode(texts).tolist()
        points = []

        # 2. Prepare Points
        for i, (text, meta, vector) in enumerate(zip(texts, metadatas, embeddings)):
            point_id = str(uuid.uuid4())
            
            # Combine metadata + text + source for easy filtering
            payload = {**meta, "text": text, "source": filename}
            
            points.append(PointStruct(id=point_id, vector=vector, payload=payload))

        # 3. Upload Batch
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
        print(f"   -> Indexed {len(points)} chunks in Qdrant.")

    def search(self, query: str, limit: int = 15, filters: Dict[str, Any] = None) -> List[Dict]:
        """Semantic search using query_points with optional filters."""
        query_vector = self.embedding_model.encode(query).tolist()
        
        # Build Qdrant Filter
        query_filter = None
        if filters:
            conditions = []
            for key, value in filters.items():
                if isinstance(value, list):
                    # Filter by ANY in list (e.g. source in [file1, file2])
                    conditions.append(FieldCondition(key=key, match=MatchAny(any=value)))
                else:
                    # Filter by exact match
                    conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
            
            if conditions:
                query_filter = Filter(must=conditions)

        search_result = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=query_filter, # Apply the filter here
            limit=limit,
            with_payload=True
        ).points
        
        # Convert Qdrant format to simple Dict for our app
        formatted = []
        for hit in search_result:
            formatted.append({
                "text": hit.payload.get("text", ""),
                "metadata": {k:v for k,v in hit.payload.items() if k != "text"},
                "score": hit.score
            })
        return formatted

    def delete_file(self, filename: str):
        """Deletes vectors for a specific file."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
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