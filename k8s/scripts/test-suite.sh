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
#
# KNOWN GAP: NVIDIA NIM API reachability is NOT tested here.
# kubectl-level tests cannot verify that NVIDIA_API_KEY is valid
# or that the NIM endpoints (embed, rerank, LLM) are reachable.
# After deploy, verify manually:
#   kubectl logs deployment/fastapi | grep -E 'NVIDIA|ERROR|Ready'
#   kubectl logs deployment/worker  | grep -E 'NVIDIA|ERROR|Ready'
# A green test suite does not guarantee the API stack is functional.
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
# Ollama removed from stack — no longer tested
echo ""

# ── 2. SERVICE ENDPOINTS ──
echo "── 2. Service Endpoints ──"
test_service "fastapi-service"
test_service "redis-service"
test_service "qdrant-service"
test_service "neo4j-service"
test_service "minio-service"
echo ""

# ── 3. HTTP HEALTH CHECKS ──
echo "── 3. HTTP Health Checks (via port-forward) ──"

kubectl port-forward svc/fastapi-service 18000:8000 &>/dev/null &
PF_PID=$!
sleep 2
test_http "FastAPI /health" "http://localhost:18000/health" "200"
kill $PF_PID 2>/dev/null
wait $PF_PID 2>/dev/null

kubectl port-forward svc/qdrant-service 16333:6333 &>/dev/null &
PF_PID=$!
sleep 2
test_http "Qdrant /healthz" "http://localhost:16333/healthz" "200"
kill $PF_PID 2>/dev/null
wait $PF_PID 2>/dev/null

kubectl port-forward svc/minio-service 19000:9000 &>/dev/null &
PF_PID=$!
sleep 2
test_http "MinIO /minio/health/live" "http://localhost:19000/minio/health/live" "200"
kill $PF_PID 2>/dev/null
wait $PF_PID 2>/dev/null

echo ""

# ── 4. INGRESS ROUTING ──
echo "── 4. Ingress Routing (via documind.local) ──"

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
echo ""
echo -e " ${YELLOW}REMINDER: Verify NVIDIA NIM API connectivity separately:${NC}"
echo "   kubectl logs deployment/fastapi | grep -E 'NVIDIA|embed|rerank|ERROR|Ready'"
echo "═══════════════════════════════════════════════"
echo ""

exit $FAILED
