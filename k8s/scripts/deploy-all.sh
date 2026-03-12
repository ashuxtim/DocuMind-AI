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
kubectl apply -f k8s/base/redis-pvc.yaml 
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
kubectl wait --for=condition=available deployment/fastapi --timeout=240s 2>/dev/null && \
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