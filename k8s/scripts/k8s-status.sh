#!/bin/bash
# DocuMind K8s Status Check
# Run this anytime to see the state of your cluster

echo "═══════════════════════════════════════════"
echo " 🎯 DocuMind Kubernetes Status"
echo "═══════════════════════════════════════════"

echo ""
echo "── Cluster ──────────────────────────────"
kubectl cluster-info 2>/dev/null | head -1

echo ""
echo "── Nodes ────────────────────────────────"
kubectl get nodes

echo ""
echo "── Deployments ──────────────────────────"
kubectl get deployments

echo ""
echo "── StatefulSets ─────────────────────────"
kubectl get statefulsets

echo ""
echo "── PersistentVolumeClaims ─────────────────"
kubectl get pvc

echo ""
echo "── Pods ─────────────────────────────────"
kubectl get pods -o wide

echo ""
echo "── Services ─────────────────────────────"
kubectl get services

echo ""
echo "── Endpoints ────────────────────────────"
kubectl get endpoints

echo ""
echo "═══════════════════════════════════════════"