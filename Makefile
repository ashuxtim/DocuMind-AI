# DocuMind - Makefile
# Usage: make <target>

BACKEND_IMAGE := documind-fastapi:v2.0
ENV_FILE      := ./backend/.env

# ── Secrets (sync .env → K8s) ───────────────────────────────────────────────
# Run this once on fresh cluster and any time you change .env.
# Idempotent — safe to run multiple times.
secrets:
	@echo "🔑 Syncing $(ENV_FILE) → K8s secret documind-secrets..."
	@if [ ! -f $(ENV_FILE) ]; then \
		echo "❌ $(ENV_FILE) not found — create it first"; exit 1; \
	fi
	@kubectl create secret generic documind-secrets \
		--from-env-file=$(ENV_FILE) \
		--dry-run=client -o yaml | kubectl apply -f -
	@echo "✅ Secret synced"

minio-secret:
	@echo "🔑 Creating minio-credentials secret..."
	@MINIO_ACCESS_KEY=$$(grep '^MINIO_ACCESS_KEY=' $(ENV_FILE) | cut -d= -f2- | tr -d '[:space:]'); \
		MINIO_SECRET_KEY=$$(grep '^MINIO_SECRET_KEY=' $(ENV_FILE) | cut -d= -f2- | tr -d '[:space:]'); \
		kubectl create secret generic minio-credentials \
			--from-literal=root_user="$$MINIO_ACCESS_KEY" \
			--from-literal=root_password="$$MINIO_SECRET_KEY" \
			--dry-run=client -o yaml | kubectl apply -f -
	@echo "✅ minio-credentials ready"

# ── Build ──────────────────────────────────────────────────────────────
build:
	@echo "🔨 Building backend image $(BACKEND_IMAGE)..."
	@eval $$(minikube docker-env) && \
		DOCKER_BUILDKIT=1 docker build \
		--progress=plain \
		--build-arg CACHEBUST=$$(date +%s) \
		-t $(BACKEND_IMAGE) ./backend
	@echo "✅ Backend image built"

# ── Deploy ─────────────────────────────────────────────────────────────
deploy:
	@echo "🚀 Restarting backend + worker..."
	@kubectl rollout restart deployment fastapi worker
	@kubectl rollout status deployment fastapi worker
	@echo "✅ Deployed"

# ── Build + Deploy ──────────────────────────────────────────────────────
backend: build deploy

# ── Fresh cluster setup (run once after minikube start) ─────────────────
# Order: secrets → minio secret → deploy all
setup: secrets minio-secret
	@echo "🚀 Deploying full stack..."
	@bash k8s/scripts/deploy-all.sh
	@echo "✅ Stack deployed — check logs with: make check-llm"

# ── Sync secrets + restart (run after changing .env) ────────────────────
fresh: secrets deploy
	@echo "✅ Secrets synced + pods restarted"

# ── Status ──────────────────────────────────────────────────────────────
pods:
	@kubectl get pods -w

status:
	@kubectl get deployments
	@echo ""
	@kubectl get pods

# ── Logs ────────────────────────────────────────────────────────────────
logs:
	@kubectl logs deployment/fastapi --follow | grep -v "/health" | grep -v "/status"

logs-worker:
	@kubectl logs deployment/worker --follow | grep -v "/health" | grep -v "/status"

logs-all:
	@stern . --namespace default | grep -vE "GET /(health|status)"

# ── LLM check ───────────────────────────────────────────────────────────
check-llm:
	@kubectl logs deployment/fastapi | grep -E "Initializing|LLM Ready|ERROR|NVIDIA"

# ── Wipe individual stores ───────────────────────────────────────────────
wipe-qdrant:
	@echo "🗑️  Wiping Qdrant collection..."
	@QDRANT_PORT=$$(grep '^QDRANT_PORT=' $(ENV_FILE) | cut -d= -f2- | tr -d '[:space:]'); \
		if [ -z "$$QDRANT_PORT" ]; then \
			echo "❌ QDRANT_PORT not found in $(ENV_FILE)"; exit 1; \
		fi; \
		kubectl port-forward svc/qdrant-service $$QDRANT_PORT:$$QDRANT_PORT & \
		PF_PID=$$!; \
		sleep 2; \
		curl -s -X DELETE http://localhost:$$QDRANT_PORT/collections/documind_docs; \
		kill $$PF_PID
	@echo "✅ Qdrant wiped"

wipe-neo4j:
	@echo "🗑️  Wiping Neo4j..."
	@NEO4J_PASSWORD=$$(grep '^NEO4J_PASSWORD=' $(ENV_FILE) | cut -d= -f2- | tr -d '[:space:]'); \
		if [ -z "$$NEO4J_PASSWORD" ]; then \
			echo "❌ NEO4J_PASSWORD not found in $(ENV_FILE)"; exit 1; \
		fi; \
		kubectl exec -it neo4j-0 -- cypher-shell -u neo4j -p "$$NEO4J_PASSWORD" \
			"MATCH (n) DETACH DELETE n" 2>/dev/null | tail -1
	@echo "✅ Neo4j wiped"

wipe-redis:
	@echo "🗑️  Wiping Redis..."
	@kubectl exec -it $$(kubectl get pod -l app=redis \
		-o jsonpath='{.items[0].metadata.name}') -- redis-cli FLUSHALL
	@echo "✅ Redis wiped"

wipe-minio:
	@echo "🗑️  Wiping Minio uploads..."
	@MINIO_ACCESS_KEY=$$(grep '^MINIO_ACCESS_KEY=' $(ENV_FILE) | cut -d= -f2- | tr -d '[:space:]'); \
		MINIO_SECRET_KEY=$$(grep '^MINIO_SECRET_KEY=' $(ENV_FILE) | cut -d= -f2- | tr -d '[:space:]'); \
		if [ -z "$$MINIO_ACCESS_KEY" ] || [ -z "$$MINIO_SECRET_KEY" ]; then \
			echo "❌ MINIO_ACCESS_KEY or MINIO_SECRET_KEY not found in $(ENV_FILE)"; exit 1; \
		fi; \
		kubectl exec -it minio-0 -- mc alias set local \
			http://localhost:9000 "$$MINIO_ACCESS_KEY" "$$MINIO_SECRET_KEY" 2>/dev/null; \
		kubectl exec -it minio-0 -- mc rm --recursive --force local/documind-uploads
	@echo "✅ Minio wiped"

# ── Wipe everything ──────────────────────────────────────────────────────
wipe-all: wipe-qdrant wipe-neo4j wipe-redis wipe-minio
	@echo "✅ All stores wiped"

# ── Full reset (wipe + restart) ───────────────────────────────────────────
reset: wipe-all deploy
	@echo "✅ Full reset complete"

# ── Restart ALL pods ─────────────────────────────────────────────────────
restart-all:
	@echo "🔄 Restarting all deployments..."
	@kubectl get deployments -o name | xargs kubectl rollout restart
	@kubectl get deployments -o name | xargs -I {} kubectl rollout status {}
	@echo "✅ All pods restarted"
