# Phase 6 — Automation, Testing & Documentation: Production Ready

You've deployed all 6 services to Kubernetes. But right now, deploying the stack means running 12+ `kubectl apply` commands in the right order. Deleting it means remembering every resource. And verifying it means manually curling endpoints. **That's not production-ready.**

This final phase adds the polish that separates a learning exercise from a professional deployment: automated deployment scripts, a test suite, a debugging guide, and clean documentation. You'll also update the `k8s-status.sh` script from Phase 3 to cover the full stack.

---

## Step 1: Theory — Why Automation Matters

### 1.1 The "Works on My Machine" Problem

Without automation:
```
Developer A:  "Just run kubectl apply on all the YAMLs"
Developer B:  "In what order?"
Developer A:  "Secrets first, then services, then statefulsets, wait for them, then deployments"
Developer B:  "Which secrets? I'm missing minio-credentials."
Developer A:  "Oh, you need to create those manually first."

                                 → 45 minutes later, Developer B is still debugging 😤
```

With automation:
```
Developer B:  ./k8s/scripts/deploy-all.sh
                                 → 3 minutes later, everything is running 🎉
```

### 1.2 What We'll Build

```
k8s/scripts/
├── deploy-all.sh          ← Deploy entire stack in correct order
├── delete-all.sh          ← Clean teardown with PVC protection
├── test-suite.sh          ← Automated health checks for all services
├── k8s-status.sh          ← Updated from Phase 3 with full stack view
└── backup-neo4j.sh        ← Already created in Phase 4
```

---

## Step 2: Create the Deploy Script

This script deploys the entire DocuMind stack from scratch, in the correct dependency order, with pre-flight checks and wait conditions.

Create the file `k8s/scripts/deploy-all.sh`:

```bash
#!/bin/bash
# ─── deploy-all.sh ──────────────────────────────────────────────
# Deploy the entire DocuMind stack to Kubernetes.
#
# DEPENDENCY ORDER:
# 1. Secrets (must exist before pods reference them)
# 2. ConfigMaps (must exist before pods reference them)
# 3. Headless Services (must exist before StatefulSets)
# 4. Regular Services (for ClusterIP access)
# 5. StatefulSets (databases start first — pods need time)
# 6. Deployments (app connects to databases)
# 7. Ingress (routing layer — everything must be running)
#
# WHY ORDER MATTERS:
# StatefulSets reference Headless Services in .spec.serviceName.
# Pods reference Secrets and ConfigMaps in env/volumeMounts.
# If these don't exist at apply time, pods fail to start.
# ────────────────────────────────────────────────────────────────

set -e  # Exit on any error

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo ""
echo "═══════════════════════════════════════════════"
echo " 🚀 Deploying DocuMind to Kubernetes"
echo "═══════════════════════════════════════════════"
echo ""

# ── PRE-FLIGHT CHECKS ──
echo "── Pre-flight Checks ──"

# Check kubectl is connected
if ! kubectl cluster-info &>/dev/null; then
    echo -e "${RED}ERROR: kubectl cannot connect to cluster.${NC}"
    echo "  Run: minikube start"
    exit 1
fi
echo -e "  ${GREEN}✅ Cluster is reachable${NC}"

# Check required secrets exist
MISSING_SECRETS=0
for secret in documind-secrets minio-credentials; do
    if ! kubectl get secret "$secret" &>/dev/null; then
        echo -e "  ${RED}❌ Missing secret: $secret${NC}"
        MISSING_SECRETS=1
    else
        echo -e "  ${GREEN}✅ Secret exists: $secret${NC}"
    fi
done

if [ $MISSING_SECRETS -eq 1 ]; then
    echo ""
    echo -e "${YELLOW}Create missing secrets before deploying:${NC}"
    echo "  kubectl create secret generic documind-secrets \\"
    echo "    --from-literal=GEMINI_API_KEY=your-key \\"
    echo "    --from-literal=NEO4J_PASSWORD=password"
    echo ""
    echo "  kubectl create secret generic minio-credentials \\"
    echo "    --from-literal=root_user=admin \\"
    echo "    --from-literal=root_password=minioadmin123"
    echo ""
    exit 1
fi

# Check Docker image is available
if minikube image ls 2>/dev/null | grep -q "documind"; then
    echo -e "  ${GREEN}✅ DocuMind image found in Minikube${NC}"
else
    echo -e "  ${YELLOW}⚠️  DocuMind image not found — pods may use remote registry${NC}"
fi

echo ""

# ── STEP 1: ConfigMaps ──
echo "── Step 1: ConfigMaps ──"
kubectl apply -f k8s/base/documind-configmap.yaml
echo -e "  ${GREEN}✅ ConfigMap applied${NC}"
echo ""

# ── STEP 2: Services (all of them — Headless + Regular) ──
echo "── Step 2: Services ──"
kubectl apply -f k8s/base/redis-service.yaml
kubectl apply -f k8s/base/qdrant-headless-service.yaml
kubectl apply -f k8s/base/qdrant-service.yaml
kubectl apply -f k8s/base/neo4j-headless-service.yaml
kubectl apply -f k8s/base/neo4j-service.yaml
kubectl apply -f k8s/base/minio-headless-service.yaml
kubectl apply -f k8s/base/minio-service.yaml
kubectl apply -f k8s/base/fastapi-service.yaml
echo -e "  ${GREEN}✅ All services applied${NC}"
echo ""

# ── STEP 3: StatefulSets (databases — start first) ──
echo "── Step 3: StatefulSets (databases) ──"
kubectl apply -f k8s/base/redis-deployment.yaml
kubectl apply -f k8s/base/qdrant-statefulset.yaml
kubectl apply -f k8s/base/neo4j-statefulset.yaml
kubectl apply -f k8s/base/minio-statefulset.yaml

echo "  Waiting for databases to be ready..."
kubectl wait --for=condition=ready pod -l app=redis --timeout=120s 2>/dev/null && \
    echo -e "  ${GREEN}✅ Redis ready${NC}" || echo -e "  ${RED}❌ Redis timeout${NC}"

kubectl wait --for=condition=ready pod -l app=qdrant --timeout=120s 2>/dev/null && \
    echo -e "  ${GREEN}✅ Qdrant ready${NC}" || echo -e "  ${RED}❌ Qdrant timeout${NC}"

kubectl wait --for=condition=ready pod -l app=neo4j --timeout=180s 2>/dev/null && \
    echo -e "  ${GREEN}✅ Neo4j ready${NC}" || echo -e "  ${RED}❌ Neo4j timeout (JVM startup is slow)${NC}"

kubectl wait --for=condition=ready pod -l app=minio --timeout=120s 2>/dev/null && \
    echo -e "  ${GREEN}✅ MinIO ready${NC}" || echo -e "  ${RED}❌ MinIO timeout${NC}"
echo ""

# ── STEP 4: Deployments (app layer — needs databases) ──
echo "── Step 4: Deployments (application) ──"
kubectl apply -f k8s/base/fastapi-deployment.yaml
kubectl apply -f k8s/base/worker-deployment.yaml

echo "  Waiting for application pods..."
kubectl wait --for=condition=available deployment/fastapi --timeout=120s 2>/dev/null && \
    echo -e "  ${GREEN}✅ FastAPI ready${NC}" || echo -e "  ${RED}❌ FastAPI timeout${NC}"

kubectl wait --for=condition=available deployment/worker --timeout=120s 2>/dev/null && \
    echo -e "  ${GREEN}✅ Celery worker ready${NC}" || echo -e "  ${RED}❌ Worker timeout${NC}"
echo ""

# ── STEP 5: Ingress ──
echo "── Step 5: Ingress ──"
kubectl apply -f k8s/base/ingress.yaml
echo -e "  ${GREEN}✅ Ingress applied${NC}"
echo ""

# ── SUMMARY ──
echo "═══════════════════════════════════════════════"
echo -e " ${GREEN}🎉 Deployment Complete!${NC}"
echo "═══════════════════════════════════════════════"
echo ""
echo " Access DocuMind at:"
echo "   API:    http://documind.local/api/health"
echo "   Qdrant: http://documind.local/qdrant/healthz"
echo "   Neo4j:  http://documind.local/neo4j/"
echo "   MinIO:  http://documind.local/minio/"
echo ""
echo " Quick check: curl http://documind.local/api/health"
echo ""
```

Make it executable:
```bash
chmod +x k8s/scripts/deploy-all.sh
```

> **📖 Why `set -e`?**
> This tells bash to exit immediately if any command fails. Without it, the script would continue deploying even if a critical step (like creating ConfigMaps) failed, leading to cascading errors that are harder to debug. It's a shell scripting best practice for deployment scripts.

---

## Step 3: Create the Delete Script

This script cleanly tears down all resources with a safety prompt before deleting PVCs (which contain your data!).

Create the file `k8s/scripts/delete-all.sh`:

```bash
#!/bin/bash
# ─── delete-all.sh ──────────────────────────────────────────────
# Tear down the entire DocuMind stack from Kubernetes.
#
# ORDER: Reverse of deploy — top-down teardown
# 1. Ingress (stop external traffic first)
# 2. Deployments (stop app layer)
# 3. StatefulSets (stop databases — PVCs are preserved!)
# 4. Services (stop routing)
# 5. ConfigMaps (optional)
# 6. PVCs (⚠️ ONLY if user confirms — contains data!)
#
# WHY PVCs ARE KEPT:
# Deleting a StatefulSet does NOT delete its PVCs.
# This is intentional — your database data survives.
# Only delete PVCs if you want a truly clean slate.
# ────────────────────────────────────────────────────────────────

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "═══════════════════════════════════════════════"
echo " 🗑️  Deleting DocuMind from Kubernetes"
echo "═══════════════════════════════════════════════"
echo ""

# Step 1: Ingress
echo "── Step 1: Removing Ingress ──"
kubectl delete -f k8s/base/ingress.yaml --ignore-not-found=true
echo -e "  ${GREEN}✅ Ingress removed${NC}"

# Step 2: Deployments
echo "── Step 2: Removing Deployments ──"
kubectl delete -f k8s/base/fastapi-deployment.yaml --ignore-not-found=true
kubectl delete -f k8s/base/worker-deployment.yaml --ignore-not-found=true
echo -e "  ${GREEN}✅ Deployments removed${NC}"

# Step 3: StatefulSets (PVCs are kept!)
echo "── Step 3: Removing StatefulSets ──"
kubectl delete -f k8s/base/qdrant-statefulset.yaml --ignore-not-found=true
kubectl delete -f k8s/base/neo4j-statefulset.yaml --ignore-not-found=true
kubectl delete -f k8s/base/minio-statefulset.yaml --ignore-not-found=true
kubectl delete -f k8s/base/redis-deployment.yaml --ignore-not-found=true
echo -e "  ${GREEN}✅ StatefulSets removed (PVCs preserved)${NC}"

# Step 4: Services
echo "── Step 4: Removing Services ──"
kubectl delete -f k8s/base/fastapi-service.yaml --ignore-not-found=true
kubectl delete -f k8s/base/redis-service.yaml --ignore-not-found=true
kubectl delete -f k8s/base/qdrant-headless-service.yaml --ignore-not-found=true
kubectl delete -f k8s/base/qdrant-service.yaml --ignore-not-found=true
kubectl delete -f k8s/base/neo4j-headless-service.yaml --ignore-not-found=true
kubectl delete -f k8s/base/neo4j-service.yaml --ignore-not-found=true
kubectl delete -f k8s/base/minio-headless-service.yaml --ignore-not-found=true
kubectl delete -f k8s/base/minio-service.yaml --ignore-not-found=true
echo -e "  ${GREEN}✅ Services removed${NC}"

# Step 5: ConfigMaps
echo "── Step 5: Removing ConfigMaps ──"
kubectl delete -f k8s/base/documind-configmap.yaml --ignore-not-found=true
echo -e "  ${GREEN}✅ ConfigMaps removed${NC}"

echo ""

# Step 6: PVCs (with safety prompt)
echo "── Step 6: Persistent Volume Claims ──"
echo ""
echo "  Current PVCs:"
kubectl get pvc --no-headers 2>/dev/null | awk '{printf "    %-40s %s\n", $1, $4}' || echo "    (none)"
echo ""
echo -e "  ${YELLOW}⚠️  Deleting PVCs will PERMANENTLY DESTROY all database data.${NC}"
echo -e "  ${YELLOW}   This includes Qdrant vectors, Neo4j graphs, MinIO files, and Redis data.${NC}"
echo ""
read -p "  Delete ALL PVCs? (y/N): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    kubectl delete pvc --all
    echo -e "  ${RED}🗑️  All PVCs deleted${NC}"
else
    echo -e "  ${GREEN}✅ PVCs preserved — data is safe${NC}"
    echo "  To delete PVCs later: kubectl delete pvc --all"
fi

echo ""
echo "═══════════════════════════════════════════════"
echo -e " ${GREEN}✅ Teardown Complete${NC}"
echo "═══════════════════════════════════════════════"
echo ""

# Show remaining resources
REMAINING=$(kubectl get all --no-headers 2>/dev/null | grep -v "kubernetes" | wc -l)
if [ "$REMAINING" -eq 0 ]; then
    echo " No DocuMind resources remaining (clean slate)."
else
    echo " Remaining resources:"
    kubectl get all 2>/dev/null | grep -v "kubernetes"
fi
echo ""
```

Make it executable:
```bash
chmod +x k8s/scripts/delete-all.sh
```

> **📖 Key design decisions:**
> - `--ignore-not-found=true` prevents errors if a resource was already deleted
> - PVCs require explicit confirmation because **data loss is irreversible**
> - Reverse order ensures no dangling references during teardown

---

## Step 4: Create the Test Suite

This script programmatically verifies every component of your deployment — pods, services, and endpoints.

Create the file `k8s/scripts/test-suite.sh`:

```bash
#!/bin/bash
# ─── test-suite.sh ──────────────────────────────────────────────
# Automated test suite to verify the entire DocuMind K8s stack.
# Run after deploy-all.sh to confirm everything works.
#
# TESTS:
# 1. Pod health — correct number running for each app
# 2. Service endpoints — each service has backend pods
# 3. HTTP health checks — each service responds correctly
# 4. Ingress routing — all paths resolve via documind.local
# 5. Persistence — PVCs are bound
# ────────────────────────────────────────────────────────────────

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'
PASSED=0
FAILED=0

pass() {
    echo -e "  ${GREEN}✅ PASS${NC}: $1"
    PASSED=$((PASSED + 1))
}

fail() {
    echo -e "  ${RED}❌ FAIL${NC}: $1"
    FAILED=$((FAILED + 1))
}

warn() {
    echo -e "  ${YELLOW}⚠️  WARN${NC}: $1"
}

# ── Test function: Check pod count ──
test_pods() {
    local app=$1
    local expected=$2
    local count
    count=$(kubectl get pods -l app="$app" --no-headers 2>/dev/null | grep -c "Running")

    if [ "$count" -eq "$expected" ]; then
        pass "$app: $count/$expected pods running"
    else
        fail "$app: $count/$expected pods running"
    fi
}

# ── Test function: Check service has endpoints ──
test_service() {
    local svc=$1
    local endpoints
    endpoints=$(kubectl get endpoints "$svc" --no-headers 2>/dev/null | awk '{print $2}')

    if [ -n "$endpoints" ] && [ "$endpoints" != "<none>" ]; then
        pass "$svc: has endpoints ($endpoints)"
    else
        fail "$svc: no endpoints (no pods matching selector)"
    fi
}

# ── Test function: HTTP health check ──
test_http() {
    local name=$1
    local url=$2
    local expected_code=$3
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$url" 2>/dev/null)

    if [ "$code" = "$expected_code" ]; then
        pass "$name: HTTP $code"
    else
        fail "$name: expected HTTP $expected_code, got $code"
    fi
}

# ── Test function: Check PVC is Bound ──
test_pvc() {
    local pvc=$1
    local status
    status=$(kubectl get pvc "$pvc" --no-headers 2>/dev/null | awk '{print $2}')

    if [ "$status" = "Bound" ]; then
        pass "$pvc: Bound"
    else
        fail "$pvc: status is '$status' (expected Bound)"
    fi
}

echo ""
echo "═══════════════════════════════════════════════"
echo " 🧪 DocuMind K8s Test Suite"
echo "═══════════════════════════════════════════════"
echo ""

# ── 1. POD HEALTH ──
echo "── 1. Pod Health ──"
test_pods "fastapi" 2
test_pods "worker" 1
test_pods "redis" 1
test_pods "qdrant" 1
test_pods "neo4j" 1
test_pods "minio" 1
echo ""

# ── 2. SERVICE ENDPOINTS ──
echo "── 2. Service Endpoints ──"
test_service "fastapi-service"
test_service "redis-service"
test_service "qdrant-service"
test_service "neo4j-service"
test_service "minio-service"
echo ""

# ── 3. DIRECT HTTP HEALTH CHECKS ──
echo "── 3. HTTP Health Checks (via port-forward) ──"

# FastAPI — via port-forward
kubectl port-forward svc/fastapi-service 18000:8000 &>/dev/null &
PF_PID=$!
sleep 2
test_http "FastAPI /health" "http://localhost:18000/health" "200"
kill $PF_PID 2>/dev/null
wait $PF_PID 2>/dev/null

# Qdrant — via port-forward
kubectl port-forward svc/qdrant-service 16333:6333 &>/dev/null &
PF_PID=$!
sleep 2
test_http "Qdrant /healthz" "http://localhost:16333/healthz" "200"
kill $PF_PID 2>/dev/null
wait $PF_PID 2>/dev/null

# MinIO — via port-forward
kubectl port-forward svc/minio-service 19000:9000 &>/dev/null &
PF_PID=$!
sleep 2
test_http "MinIO /minio/health/live" "http://localhost:19000/minio/health/live" "200"
kill $PF_PID 2>/dev/null
wait $PF_PID 2>/dev/null

echo ""

# ── 4. INGRESS ROUTING ──
echo "── 4. Ingress Routing (via documind.local) ──"

# Check if documind.local resolves
if ping -c 1 -W 2 documind.local &>/dev/null; then
    test_http "Ingress /api/health" "http://documind.local/api/health" "200"
    test_http "Ingress /qdrant/healthz" "http://documind.local/qdrant/healthz" "200"
else
    warn "documind.local does not resolve — skipping Ingress tests"
    warn "Add to /etc/hosts: $(minikube ip 2>/dev/null || echo '<minikube-ip>')  documind.local"
fi
echo ""

# ── 5. PERSISTENCE ──
echo "── 5. Persistent Volume Claims ──"
# Check common PVC names — yours may differ slightly
for pvc in $(kubectl get pvc --no-headers 2>/dev/null | awk '{print $1}'); do
    test_pvc "$pvc"
done
echo ""

# ── SUMMARY ──
TOTAL=$((PASSED + FAILED))
echo "═══════════════════════════════════════════════"
if [ $FAILED -eq 0 ]; then
    echo -e " ${GREEN}🎉 All $TOTAL tests passed!${NC}"
else
    echo -e " ${RED}❌ $FAILED/$TOTAL tests failed${NC}"
    echo ""
    echo " Debug failing tests:"
    echo "   kubectl describe pod <pod-name>"
    echo "   kubectl logs <pod-name>"
    echo "   kubectl get events --sort-by='.lastTimestamp'"
fi
echo "═══════════════════════════════════════════════"
echo ""

exit $FAILED
```

Make it executable:
```bash
chmod +x k8s/scripts/test-suite.sh
```

> **📖 Design notes:**
> - Uses high port numbers (18000, 16333) for port-forwards to avoid conflicts
> - Properly kills port-forward processes after each test
> - Exit code = number of failures (0 = success, usable in CI pipelines)
> - PVC test is dynamic — discovers all PVCs instead of hardcoding names

---

## Step 5: Update the Status Script

Update `k8s/scripts/k8s-status.sh` to show the complete stack including MinIO and Ingress:

```bash
#!/bin/bash
# ─── k8s-status.sh ──────────────────────────────────────────────
# One-command overview of the entire DocuMind K8s deployment.
# Updated in Phase 6 to include MinIO, Ingress, and resource usage.
# ────────────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════"
echo " 📊 DocuMind K8s — Full Stack Status"
echo "═══════════════════════════════════════════════"

echo ""
echo "── Deployments ──"
kubectl get deployments -o wide 2>/dev/null || echo "  (none)"

echo ""
echo "── StatefulSets ──"
kubectl get statefulsets -o wide 2>/dev/null || echo "  (none)"

echo ""
echo "── Pods ──"
kubectl get pods -o wide 2>/dev/null || echo "  (none)"

echo ""
echo "── Services ──"
kubectl get services 2>/dev/null || echo "  (none)"

echo ""
echo "── Ingress ──"
kubectl get ingress 2>/dev/null || echo "  (none)"

echo ""
echo "── PVCs ──"
kubectl get pvc 2>/dev/null || echo "  (none)"

echo ""
echo "── ConfigMaps ──"
kubectl get configmaps 2>/dev/null | grep -v "kube-" || echo "  (none)"

echo ""
echo "── Secrets ──"
kubectl get secrets 2>/dev/null | grep -v "default-token\|kubernetes.io" || echo "  (none)"

echo ""
echo "── Resource Usage ──"
kubectl top pods 2>/dev/null || echo "  (enable: minikube addons enable metrics-server)"

echo ""
echo "── Recent Events (last 10) ──"
kubectl get events --sort-by='.lastTimestamp' 2>/dev/null | tail -10 || echo "  (none)"

echo ""
echo "═══════════════════════════════════════════════"
echo ""
```

Make it executable (if not already):
```bash
chmod +x k8s/scripts/k8s-status.sh
```

---

## Step 6: Create the Architecture Document

Create the file `k8s/ARCHITECTURE.md`:

```markdown
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
```

---

## Step 7: Create the README

Create the file `k8s/README.md`:

```markdown
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
```

---

## Step 8: Create the K8s Cheat Sheet

Create the file `k8s/CHEATSHEET.md`:

```markdown
# Kubernetes Command Cheat Sheet

## Cluster
```bash
kubectl cluster-info              # Cluster endpoint
kubectl get nodes                 # List nodes
minikube status                   # Minikube health
minikube dashboard                # Web UI
```

## Pods
```bash
kubectl get pods                  # List all pods
kubectl get pods -o wide          # With node + IP
kubectl get pods -l app=fastapi   # Filter by label
kubectl describe pod <name>       # Full details + events
kubectl logs <name>               # Container logs
kubectl logs <name> --previous    # Logs from crashed container
kubectl logs -f <name>            # Follow (tail -f)
kubectl exec -it <name> -- bash   # Shell into pod
kubectl delete pod <name>         # Delete (Deployment recreates it)
```

## Deployments
```bash
kubectl get deployments                              # List
kubectl scale deployment <name> --replicas=3         # Scale
kubectl set image deployment/<name> <c>=<img>        # Update image
kubectl rollout status deployment/<name>             # Watch rollout
kubectl rollout undo deployment/<name>               # Rollback
```

## StatefulSets
```bash
kubectl get statefulsets                             # List
kubectl scale statefulset <name> --replicas=3        # Scale (ordered!)
kubectl delete statefulset <name>                    # Delete (keeps PVCs)
```

## Services
```bash
kubectl get services                                 # List
kubectl get endpoints <name>                         # Backend pod IPs
kubectl port-forward svc/<name> 8000:8000            # Local tunnel
```

## Ingress
```bash
kubectl get ingress                                  # List
kubectl describe ingress <name>                      # Rules + annotations
```

## Config & Secrets
```bash
kubectl get configmaps                               # List ConfigMaps
kubectl describe configmap <name>                    # View contents
kubectl get secrets                                  # List Secrets
kubectl get secret <name> -o jsonpath='{.data}'      # View (base64)
```

## Storage
```bash
kubectl get pvc                                      # List PVCs
kubectl get pv                                       # List PVs
kubectl describe pvc <name>                          # Binding details
```

## Debugging
```bash
kubectl describe pod <name>                          # Events + status
kubectl logs <name> --previous                       # Crashed container
kubectl get events --sort-by='.lastTimestamp'         # Recent events
kubectl top pods                                     # Resource usage
kubectl run debug --image=busybox -it --rm -- sh     # Debug pod
```

## Minikube
```bash
minikube start --cpus=4 --memory=8192               # Start
minikube stop                                        # Pause
minikube delete                                      # Destroy cluster
minikube ip                                          # Node IP
minikube image load <image>                          # Load Docker image
minikube addons enable ingress                       # Enable addon
minikube service <name> --url                        # Get service URL
```
```

---

## Step 9: Final Full-Stack Verification

Run the complete verification flow to confirm everything works:

```bash
# 1. Check all resources
./k8s/scripts/k8s-status.sh

# 2. Run the automated test suite
./k8s/scripts/test-suite.sh

# 3. Manual quick checks
curl http://documind.local/api/health
curl http://documind.local/qdrant/healthz
```

### Bonus: Deploy From Scratch Test

The ultimate proof it works — tear down everything and redeploy:

```bash
# Tear down
./k8s/scripts/delete-all.sh
# Choose 'y' to delete PVCs for a clean slate

# Recreate secrets (deleted with the above)
kubectl create secret generic documind-secrets \
  --from-literal=GEMINI_API_KEY=your-key \
  --from-literal=NEO4J_PASSWORD=password

kubectl create secret generic minio-credentials \
  --from-literal=root_user=admin \
  --from-literal=root_password=minioadmin123

# Deploy
./k8s/scripts/deploy-all.sh

# Verify
./k8s/scripts/test-suite.sh
# Expected: 🎉 All tests passed!
```

---

## ✅ Phase 6 Checklist

### Knowledge Check
- [ ] Understand why deployment order matters (secrets → services → databases → apps → ingress)
- [ ] Know why `set -e` is used in deployment scripts
- [ ] Understand why PVCs are preserved when StatefulSets are deleted
- [ ] Know the difference between `kubectl delete` and `kubectl delete --ignore-not-found`

### Hands-On Check
```bash
# 1. Deploy script works
./k8s/scripts/deploy-all.sh
# Expected: All steps pass with ✅

# 2. Test suite passes
./k8s/scripts/test-suite.sh
# Expected: 🎉 All tests passed!

# 3. Status script shows full stack
./k8s/scripts/k8s-status.sh
# Expected: All pods, services, ingress, PVCs visible

# 4. Delete script works
./k8s/scripts/delete-all.sh
# Expected: Clean teardown with PVC prompt
```

### Files Created
- [ ] `k8s/scripts/deploy-all.sh` — One-command deployment
- [ ] `k8s/scripts/delete-all.sh` — Clean teardown with PVC protection
- [ ] `k8s/scripts/test-suite.sh` — Automated health check suite
- [ ] `k8s/scripts/k8s-status.sh` — Updated full-stack status script
- [ ] `k8s/ARCHITECTURE.md` — Deployment architecture diagram
- [ ] `k8s/README.md` — Setup and management guide
- [ ] `k8s/CHEATSHEET.md` — kubectl command reference

---

## 🎓 New Concepts This Phase

| Concept | What It Is | Why You Need It |
|---------|-----------|-----------------|
| **Deployment ordering** | Secrets → Services → Databases → Apps → Ingress | Dependencies must exist before referencing resources |
| **`set -e`** | Bash: exit on error | Prevents cascading failures in scripts |
| **`--ignore-not-found`** | kubectl: no error if resource missing | Makes delete scripts idempotent (safe to run twice) |
| **Health check automation** | Script that verifies pods + HTTP endpoints | Catches deployment issues before users do |
| **PVC preservation** | StatefulSet delete keeps PVCs | Data survives teardown — intentional K8s design |
| **Exit codes** | Script returns 0 (success) or N (N failures) | Enables CI/CD pipeline integration |
| **Port-forward in scripts** | Background `kubectl port-forward` for testing | Test ClusterIP services without Ingress |

---

## 🎓 Week 1 Complete!

You've migrated the entire DocuMind application from Docker Compose to Kubernetes:

### What You Built

| Phase | Day | What You Deployed | Key Concepts |
|-------|-----|-------------------|--------------|
| **Phase 1** | Day 1 | Cluster + first pod | K8s architecture, kubectl, namespaces |
| **Phase 2** | Day 2 | FastAPI backend | Deployments, Services, NodePort, health probes |
| **Phase 3** | Day 3 | Redis + Celery workers | ConfigMaps, Secrets, PVCs, Deployments with config |
| **Phase 4** | Days 4-5 | Qdrant + Neo4j | StatefulSets, Headless Services, VCTs, ordered pods |
| **Phase 5** | Day 6 | MinIO + Ingress | Path-based routing, NGINX controller, full networking |
| **Phase 6** | Day 7 | Scripts + Docs | Automation, testing, architecture documentation |

### Your K8s Architecture

```
                    Internet
                       ↓
              ┌─── Ingress ───┐
              │ documind.local│
              └───────┬───────┘
    ┌─────────┬───────┼───────┬──────────┐
    │ /api/*  │/qdrant│/neo4j │ /minio/* │
    ↓         ↓       ↓       ↓          │
 FastAPI   Qdrant   Neo4j   MinIO       │
 (×2)      (SS)     (SS)    (SS)        │
    ↓                                    │
  Redis ← Celery Worker                 │
  (×1)     (×1)                          │
    │                                    │
    └── 5 PVCs: 43Gi total ─────────────┘
```

### Skills You Now Have

✅ Deploy stateless apps with Deployments  
✅ Deploy databases with StatefulSets + persistent storage  
✅ Configure apps with ConfigMaps and Secrets  
✅ Route traffic with Ingress + path-based rules  
✅ Debug pods, services, and networking issues  
✅ Automate deployments and testing with scripts  
✅ Write production-quality K8s manifests  

### What's Next (Week 2 Preview)

- **Terraform** — Infrastructure as Code for cloud deployment
- **CI/CD Pipelines** — Automated build, test, deploy with GitHub Actions
- **Monitoring** — Prometheus + Grafana for observability
- **Cloud Deployment** — Move from Minikube to AWS EKS or GCP GKE

---

**Congratulations — you've completed the full Kubernetes migration! 🎉**  
Your DocuMind deployment is now production-patterned, automated, tested, and documented. This is real DevOps work, not a toy tutorial.
