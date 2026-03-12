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