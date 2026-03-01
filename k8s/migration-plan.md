# DocuMind: Docker Compose → Kubernetes Migration Plan

## Migration Order (Dependency-Based)

### Phase 2 — Day 2: Stateless Backend
1. **FastAPI backend** → Deployment (2 replicas) + NodePort Service
   - Easiest starting point — no state, no volumes
   - Will temporarily hardcode env vars (fix in Phase 3)

### Phase 3 — Day 3: Message Queue Layer
2. **Redis** → Deployment + PVC + ConfigMap
   - Needed before Celery workers can start
3. **Celery workers** → Deployment (2 replicas)
   - Connects to Redis via K8s Service DNS

### Phase 4 — Day 4-5: Databases
4. **Qdrant** → StatefulSet + Headless Service + PVC (10Gi)
5. **Neo4j** → StatefulSet + Headless Service + PVC (10Gi + 1Gi logs)

### Phase 5 — Day 6: Networking & Remaining
6. **MinIO** → StatefulSet + PVC (20Gi) [if needed]
7. **Ollama** → StatefulSet + PVC (large, for model files)
8. **Ingress** → NGINX Ingress Controller for single entry point

## Network Dependencies (Service DNS)

User → Ingress → frontend-service → Frontend Pods

Frontend Pods → fastapi-service → FastAPI Pods ↓ redis-service → Redis Pod neo4j-service → Neo4j Pod qdrant-service → Qdrant Pod ollama-service → Ollama Pod

Worker Pods → redis-service (broker) → neo4j-service, qdrant-service, ollama-service (tasks)


## Resource Budget

| Service | CPU Request | Memory Request | Storage |
|---------|------------|---------------|---------|
| FastAPI ×2 | 500m each | 512Mi each | — |
| Celery ×2 | 500m each | 512Mi each | — |
| Frontend ×1 | 100m | 128Mi | — |
| Redis ×1 | 250m | 256Mi | 2Gi |
| Qdrant ×1 | 500m | 512Mi | 10Gi |
| Neo4j ×1 | 500m | 1Gi | 11Gi |
| Ollama ×1 | 1000m | 2Gi | 20Gi |
| **Total** | **~4.5 CPU** | **~6Gi** | **43Gi** |
