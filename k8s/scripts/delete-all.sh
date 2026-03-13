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
kubectl delete -f k8s/base/ollama-statefulset.yaml --ignore-not-found=true
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
kubectl delete -f k8s/base/ollama-headless-service.yaml --ignore-not-found=true
kubectl delete -f k8s/base/ollama-service.yaml --ignore-not-found=true
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