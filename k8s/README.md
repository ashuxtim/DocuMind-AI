# DocuMind Kubernetes Deployment

Production-ready Kubernetes deployment for the DocuMind AI RAG system.

## Prerequisites

- Kubernetes cluster (Minikube recommended for local dev)
- kubectl CLI configured
- Docker image `documind-fastapi:v1.0` built and loaded
- Minimum: 4 vCPUs, 8GB RAM

## Quick Start

### 1. Start Cluster
```bash
minikube start --cpus=4 --memory=8192 --driver=docker
minikube addons enable ingress
```

### 2. Build and Load Image
```bash
eval $(minikube docker-env)
docker build -t documind-fastapi:v1.0 .
```

### 3. Create Secrets
```bash
kubectl create secret generic documind-secrets \
  --from-literal=GEMINI_API_KEY=your-key \
  --from-literal=NEO4J_PASSWORD=password

kubectl create secret generic minio-credentials \
  --from-literal=root_user=admin \
  --from-literal=root_password=minioadmin123
```

### 4. Deploy
```bash
./k8s/scripts/deploy-all.sh
```

### 5. Configure DNS
```bash
echo "$(minikube ip)  documind.local" | sudo tee -a /etc/hosts
```

### 6. Verify
```bash
./k8s/scripts/test-suite.sh
```

## Access Points

| Service | URL | Notes |
|---------|-----|-------|
| FastAPI | http://documind.local/api/health | REST API |
| Qdrant | http://documind.local/qdrant/healthz | Vector DB |
| Neo4j | http://documind.local/neo4j/ | Graph DB |
| MinIO | http://documind.local/minio/ | Object storage |

## Management

```bash
# Full status overview
./k8s/scripts/k8s-status.sh

# Run test suite
./k8s/scripts/test-suite.sh

# Scale FastAPI
kubectl scale deployment fastapi --replicas=3

# View logs
kubectl logs -l app=fastapi --tail=50 -f

# Backup Neo4j
./k8s/scripts/backup-neo4j.sh

# Tear down (preserves data by default)
./k8s/scripts/delete-all.sh
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed deployment diagram.

## Troubleshooting

| Symptom | Debug Command | Common Fix |
|---------|--------------|------------|
| Pod stuck Pending | `kubectl describe pod <name>` | Insufficient resources |
| CrashLoopBackOff | `kubectl logs <name> --previous` | Check env vars / secrets |
| Service 404 | `kubectl get endpoints <svc>` | Selector doesn't match pods |
| Ingress 404 | `kubectl describe ingress` | Check rewrite-target annotation |
| PVC unbound | `kubectl get pvc` | Check storageClassName |