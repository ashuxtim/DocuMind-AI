# DocuMind - Makefile
# Usage: make <target>

BACKEND_IMAGE := documind-fastapi:v1.1

# ── Build ──────────────────────────────────────────────────────────────
build:
	@echo "🔨 Building backend..."
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

pods:
	@kubectl get pods -w

# ── Logs ───────────────────────────────────────────────────────────────
logs:
	@kubectl logs deployment/fastapi --follow | grep -v "/health" | grep -v "/status"

logs-worker:
	@kubectl logs deployment/worker --follow | grep -v "/health" | grep -v "/status"

logs-all:
	stern . --namespace default | grep -vE "GET /(health|status)"

# ── Status ─────────────────────────────────────────────────────────────
status:
	@kubectl get deployments
	@echo ""
	@kubectl get pods

# ── LLM check ──────────────────────────────────────────────────────────
check-llm:
	@kubectl logs deployment/fastapi | grep -E "Initializing|LLM Ready"

# ── Wipe individual stores ──────────────────────────────────────────────
wipe-qdrant:
	@echo "🗑️  Wiping Qdrant collection..."
	@kubectl port-forward svc/qdrant-service 6333:6333 & \
		PF_PID=$$!; \
		sleep 2; \
		curl -s -X DELETE http://localhost:6333/collections/documind_docs; \
		kill $$PF_PID
	@echo "✅ Qdrant wiped"

wipe-neo4j:
	@echo "🗑️  Wiping Neo4j..."
	@kubectl exec -it neo4j-0 -- cypher-shell -u neo4j -p password \
		"MATCH (n) DETACH DELETE n" 2>/dev/null | tail -1
	@echo "✅ Neo4j wiped"

wipe-redis:
	@echo "🗑️  Wiping Redis..."
	@kubectl exec -it $$(kubectl get pod -l app=redis \
		-o jsonpath='{.items[0].metadata.name}') -- redis-cli FLUSHALL
	@echo "✅ Redis wiped"

wipe-minio:
	@echo "🗑️  Wiping Minio uploads..."
	@kubectl exec -it minio-0 -- mc alias set local \
		http://localhost:9000 minioadmin minioadmin123 2>/dev/null; \
		kubectl exec -it minio-0 -- mc rm --recursive --force local/documind-uploads
	@echo "✅ Minio wiped"

# ── Wipe everything ─────────────────────────────────────────────────────
wipe-all: wipe-qdrant wipe-neo4j wipe-redis wipe-minio
	@echo "✅ All stores wiped"

# ── Full reset (wipe + restart) ──────────────────────────────────────────
reset: wipe-all deploy
	@echo "✅ Full reset complete"

# ── Restart ALL pods ────────────────────────────────────────────────────────
restart-all:
	@echo "🔄 Restarting all deployments..."
	@kubectl get deployments -o name | xargs kubectl rollout restart
	@kubectl get deployments -o name | xargs -I {} kubectl rollout status {}
	@echo "✅ All pods restarted"