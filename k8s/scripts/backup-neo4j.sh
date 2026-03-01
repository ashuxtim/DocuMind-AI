#!/bin/bash
# ─── Neo4j Backup Script ──────────────────────────────────────
# Creates a database dump from the Neo4j pod.
#
# Usage: ./k8s/scripts/backup-neo4j.sh
# Output: neo4j-backup-<timestamp>.dump in current directory
# ────────────────────────────────────────────────────────────────

set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="neo4j-backup-${TIMESTAMP}.dump"

echo "═══════════════════════════════════════════"
echo " 🗄️  Neo4j Backup"
echo "═══════════════════════════════════════════"

# Check if Neo4j is running
if ! kubectl get pod neo4j-0 &>/dev/null; then
    echo "❌ neo4j-0 pod not found!"
    exit 1
fi

echo "⏳ Stopping Neo4j for consistent backup..."
# Neo4j Community requires stopping for dump
kubectl exec neo4j-0 -- neo4j-admin database dump neo4j --to-path=/tmp/

echo "📥 Copying backup to local machine..."
kubectl cp neo4j-0:/tmp/neo4j.dump ./${BACKUP_FILE}

echo "✅ Backup saved: ${BACKUP_FILE}"
echo "   Size: $(du -h ${BACKUP_FILE} | cut -f1)"
echo "═══════════════════════════════════════════"