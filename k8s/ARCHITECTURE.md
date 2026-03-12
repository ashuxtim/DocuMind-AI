# DocuMind Kubernetes Architecture

## Service Map

```
                         Internet / Browser
                               ↓
                    ┌──────────────────────┐
                    │   NGINX Ingress      │
                    │   Controller         │
                    │   (ingress-nginx ns) │
                    └──────────┬───────────┘
                               ↓
         ┌────────────────────────────────────────┐
         │         documind.local                  │
         ├────────────────────────────────────────┤
         │  /api/*     → fastapi-service:8000     │
         │  /qdrant/*  → qdrant-service:6333      │
         │  /neo4j/*   → neo4j-service:7474       │
         │  /minio/*   → minio-service:9001       │
         └────────────────────┬───────────────────┘
                              ↓
    ┌──────────┬──────────┬──────────┬──────────┐
    │ FastAPI  │  Qdrant  │  Neo4j   │  MinIO   │
    │ Deploy   │  SS      │  SS      │  SS      │
    │ (×2)     │  (×1)    │  (×1)    │  (×1)    │
    │          │  10Gi    │  10Gi+1Gi│  20Gi    │
    └────┬─────┴──────────┴──────────┴──────────┘
         ↓
    ┌──────────┐
    │  Redis   │ ← message broker + cache
    │  Deploy  │
    │  (×1)    │
    │  2Gi     │
    └────┬─────┘
         ↑
    ┌──────────┐
    │  Celery  │ ← async workers
    │  Deploy  │
    │  (×1)    │
    └──────────┘
```

## Components

| Service | K8s Resource | Replicas | Storage | Ports | Purpose |
|---------|-------------|----------|---------|-------|---------|
| FastAPI | Deployment | 2 | — | 8000 | REST API backend |
| Celery | Deployment | 1 | — | — | Async document processing |
| Redis | Deployment + PVC | 1 | 2Gi | 6379 | Message broker + cache |
| Qdrant | StatefulSet | 1 | 10Gi | 6333, 6334 | Vector database |
| Neo4j | StatefulSet | 1 | 10Gi + 1Gi | 7687, 7474 | Graph database |
| MinIO | StatefulSet | 1 | 20Gi | 9000, 9001 | S3-compatible object storage |

## Network Flow

1. **User → Ingress → FastAPI** — API requests
2. **FastAPI → Redis** — Queue async tasks
3. **Celery → Redis** — Consume tasks from queue
4. **Celery → Qdrant** — Vector similarity search
5. **Celery → Neo4j** — Graph relationship queries
6. **FastAPI/Celery → MinIO** — Document upload/download
7. **All services** — Connected via K8s ClusterIP DNS

## Configuration

| Resource | Type | Purpose |
|----------|------|---------|
| `documind-config` | ConfigMap | Service URLs, app settings |
| `documind-secrets` | Secret | API keys, passwords |
| `minio-credentials` | Secret | MinIO admin credentials |

## Storage

| PVC Name | Size | Bound To | Contains |
|----------|------|----------|----------|
| `redis-pvc` | 2Gi | Redis pod | Cache + queue data |
| `qdrant-data-qdrant-0` | 10Gi | Qdrant pod | Vector embeddings |
| `neo4j-data-neo4j-0` | 10Gi | Neo4j pod | Graph database |
| `neo4j-logs-neo4j-0` | 1Gi | Neo4j pod | Transaction logs |
| `minio-data-minio-0` | 20Gi | MinIO pod | Uploaded documents |