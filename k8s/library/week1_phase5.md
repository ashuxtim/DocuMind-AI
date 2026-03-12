# Phase 5 — Ingress & Full Stack Networking: Single Entry Point

In Phases 2-4, you accessed FastAPI via a NodePort (`30800`) and databases via `kubectl port-forward`. That works for development, but production systems need a **single entry point** with path-based routing. Today you'll deploy MinIO (the last service), set up an NGINX Ingress Controller, and access everything through `http://documind.local`.

---

## Step 1: Theory — Why Ingress Replaces NodePort

### 1.1 The Problem: Port Chaos

Right now, to access your services you need:

```
FastAPI:      http://192.168.49.2:30800       ← NodePort
Qdrant:       kubectl port-forward ... 6333    ← Manual tunnel
Neo4j:        kubectl port-forward ... 7474    ← Manual tunnel
MinIO:        kubectl port-forward ... 9001    ← Manual tunnel (not deployed yet)

4 different access methods, 4 different ports. Imagine 20 services. 😱
```

### 1.2 The Solution: One Domain, One Entry Point

With Ingress, everything goes through a single domain with path-based routing:

```
http://documind.local/api/*      → FastAPI Service (port 8000)
http://documind.local/qdrant/*   → Qdrant Service (port 6333)
http://documind.local/neo4j/*    → Neo4j Service (port 7474)
http://documind.local/minio/*    → MinIO Service (port 9001)

                                    ↑ One domain, one IP, clean paths
```

### 1.3 How Ingress Works — The Architecture

```
┌─── Your Browser ───────────────────────────────────────────────┐
│  http://documind.local/api/health                               │
└─────────────────────┬──────────────────────────────────────────┘
                      ↓
┌─── /etc/hosts ──────────────────────────────────────────────────┐
│  192.168.49.2  documind.local    ← Maps domain to Minikube IP   │
└─────────────────────┬──────────────────────────────────────────┘
                      ↓
┌─── NGINX Ingress Controller (Pod in ingress-nginx namespace) ──┐
│  Reads Ingress resources and configures NGINX reverse proxy     │
│                                                                  │
│  if path starts with /api/     → route to fastapi-service:8000  │
│  if path starts with /qdrant/  → route to qdrant-service:6333   │
│  if path starts with /neo4j/   → route to neo4j-service:7474    │
│  if path starts with /minio/   → route to minio-service:9001    │
└─────────────────────┬──────────────────────────────────────────┘
                      ↓
┌─── K8s Services ───────────────────────────────────────────────┐
│  fastapi-service → FastAPI pods (round-robin)                   │
│  qdrant-service  → Qdrant pod                                   │
│  neo4j-service   → Neo4j pod                                    │
│  minio-service   → MinIO pod                                    │
└────────────────────────────────────────────────────────────────┘
```

### 1.4 Ingress vs Service — Different Layers

| Feature | Service (NodePort) | Ingress |
|---------|-------------------|---------|
| OSI Layer | Layer 4 (TCP/UDP) | Layer 7 (HTTP/HTTPS) |
| Routing | One port → one service | Path/host rules → many services |
| SSL/TLS | Not built-in | SSL termination built-in |
| External access | One port per service (30000-32767) | Single port (80/443) |
| Load balancing | Round-robin only | Weighted, sticky, canary |
| Use case | Development, non-HTTP | **Production HTTP routing** |

> **📖 Docker Compose comparison:**
> In your `docker-compose.yml`, the frontend Nginx already does this — it reverse-proxies `/api` to the backend. Ingress is the K8s equivalent, but managed as a cluster resource with automatic service discovery via the K8s API.

---

## Step 2: Install the NGINX Ingress Controller

The Ingress Controller is the **actual NGINX reverse proxy** that reads your Ingress resources and configures routing. Without it, Ingress resources are just inert YAML — nothing processes them.

### 2.1 Enable the Minikube Ingress Addon

```bash
# Enable the NGINX Ingress Controller addon
minikube addons enable ingress

# This deploys an NGINX pod in the ingress-nginx namespace
# Wait for it to be ready (may take 30-60 seconds)
kubectl get pods -n ingress-nginx --watch
# Expected:
# ingress-nginx-controller-xxx   1/1   Running   0   30s
```

### 2.2 Verify the Controller

```bash
# Check the Ingress Controller is running
kubectl get pods -n ingress-nginx
# Expected: ingress-nginx-controller-xxx   1/1   Running

# Wait for it to be fully ready
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s
# Expected: pod/ingress-nginx-controller-xxx condition met

# Check what the controller created
kubectl get service -n ingress-nginx
# Expected: ingress-nginx-controller   NodePort/LoadBalancer
```

> **📖 What happens behind the scenes:**
> The `minikube addons enable ingress` command deploys:
> 1. An NGINX pod (the actual reverse proxy)
> 2. A Service to expose it
> 3. RBAC permissions so it can read Ingress resources
> 4. A ConfigMap for NGINX configuration
>
> The controller watches for Ingress resources across all namespaces and automatically reconfigures NGINX when they change.

---

## Step 3: Deploy MinIO (Object Storage)

MinIO is an S3-compatible object storage server. In DocuMind, it stores uploaded documents. It's the last service to deploy before we can run the full stack.

### 3.1 Create the MinIO Secret

MinIO needs credentials for its admin console. Create these imperatively (not in YAML) to avoid committing them to Git:

```bash
# Create MinIO credentials as a K8s Secret
kubectl create secret generic minio-credentials \
  --from-literal=root_user=admin \
  --from-literal=root_password=minioadmin123

# Verify
kubectl get secret minio-credentials
# Expected: minio-credentials   Opaque   2      5s
```

> **📖 Why imperative here?**
> For learning, this is simpler than another YAML file. In production, you'd use Sealed Secrets or an external secret manager. The key point is: **credentials never touch version control**.

### 3.2 Create the Headless Service

Create the file `k8s/base/minio-headless-service.yaml`:

```yaml
# ─── HEADLESS SERVICE: MinIO ──────────────────────────────────
# Required by StatefulSet for stable pod DNS.
# ────────────────────────────────────────────────────────────────

apiVersion: v1
kind: Service
metadata:
  name: minio-headless
  labels:
    app: minio
spec:
  clusterIP: None
  selector:
    app: minio
  ports:
  - name: api
    port: 9000                   # S3-compatible API
    targetPort: 9000
    protocol: TCP
  - name: console
    port: 9001                   # MinIO web console
    targetPort: 9001
    protocol: TCP
```

### 3.3 Create the Regular Service

Create the file `k8s/base/minio-service.yaml`:

```yaml
# ─── SERVICE: MinIO (Application Access) ──────────────────────
# ClusterIP Service for S3 API and console access.
# FastAPI would connect to "minio-service:9000" for object storage.
# ────────────────────────────────────────────────────────────────

apiVersion: v1
kind: Service
metadata:
  name: minio-service
  labels:
    app: minio
spec:
  type: ClusterIP
  selector:
    app: minio
  ports:
  - name: api
    port: 9000
    targetPort: 9000
    protocol: TCP
  - name: console
    port: 9001
    targetPort: 9001
    protocol: TCP
```

### 3.4 Create the StatefulSet

Create the file `k8s/base/minio-statefulset.yaml`:

```yaml
# ─── STATEFULSET: MinIO Object Storage ─────────────────────────
#
# MinIO is S3-compatible object storage. In DocuMind, it can store
# uploaded documents, making them accessible across all pods
# (solving the shared file access problem from Phase 3).
#
# WHY STATEFULSET?
# MinIO stores data on disk and needs stable identity for
# clustering (multi-node mode). Same pattern as Qdrant/Neo4j.
# ────────────────────────────────────────────────────────────────

apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: minio
  labels:
    app: minio
    component: storage
spec:
  serviceName: minio-headless
  replicas: 1
  selector:
    matchLabels:
      app: minio
  template:
    metadata:
      labels:
        app: minio
        component: storage
    spec:
      containers:
      - name: minio
        image: minio/minio:latest
        imagePullPolicy: IfNotPresent

        # ── COMMAND ──
        # MinIO needs explicit server command + console port
        args:
        - server
        - /data                    # Storage directory
        - --console-address
        - ":9001"                  # Web console on port 9001

        ports:
        - name: api
          containerPort: 9000      # S3 API
          protocol: TCP
        - name: console
          containerPort: 9001      # Web console
          protocol: TCP

        # ── CREDENTIALS FROM SECRET ──
        env:
        - name: MINIO_ROOT_USER
          valueFrom:
            secretKeyRef:
              name: minio-credentials
              key: root_user
        - name: MINIO_ROOT_PASSWORD
          valueFrom:
            secretKeyRef:
              name: minio-credentials
              key: root_password

        volumeMounts:
        - name: minio-data
          mountPath: /data

        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"

        # ── HEALTH CHECKS ──
        # MinIO has dedicated health endpoints
        livenessProbe:
          httpGet:
            path: /minio/health/live
            port: 9000
          initialDelaySeconds: 15
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3

        readinessProbe:
          httpGet:
            path: /minio/health/ready
            port: 9000
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 2

  volumeClaimTemplates:
  - metadata:
      name: minio-data
    spec:
      accessModes:
        - ReadWriteOnce
      storageClassName: standard
      resources:
        requests:
          storage: 20Gi            # Document storage — generous for uploaded files
```

### 3.5 Deploy MinIO

```bash
# Apply in order
kubectl apply -f k8s/base/minio-headless-service.yaml
kubectl apply -f k8s/base/minio-service.yaml
kubectl apply -f k8s/base/minio-statefulset.yaml

# Watch it start
kubectl get pods -l app=minio --watch
# Expected: minio-0   1/1   Running   0   15s

# Verify
kubectl get statefulset minio
kubectl get pvc -l app=minio
# Expected: minio-data-minio-0   Bound   20Gi
```

### 3.6 Test MinIO

```bash
# Port-forward the console
kubectl port-forward svc/minio-service 9001:9001 &

# Open in browser: http://localhost:9001
# Login with: admin / minioadmin123

# Test the S3 API
kubectl exec minio-0 -- curl -s http://localhost:9000/minio/health/live
# Expected: (empty 200 response)

# Stop port-forward
kill %1
```

---

## Step 4: Create the Ingress Resource

### 4.1 Configure Local DNS

Before creating the Ingress, map `documind.local` to your Minikube IP:

```bash
# Get Minikube's IP address
minikube ip
# Example output: 192.168.49.2

# Add to /etc/hosts (requires sudo)
echo "$(minikube ip)  documind.local" | sudo tee -a /etc/hosts

# Verify
ping -c 1 documind.local
# Expected: PING documind.local (192.168.49.2): 56 data bytes
```

> **📖 Why /etc/hosts?**
> This is the simplest way to make `documind.local` resolve to your Minikube cluster. In production, you'd use real DNS (Route53, Cloudflare). For local development, `/etc/hosts` is standard practice.

### 4.2 Create the Ingress YAML

Create the file `k8s/base/ingress.yaml`:

```yaml
# ─── INGRESS: DocuMind Path-Based Routing ──────────────────────
#
# Routes all traffic through a single domain with path prefixes.
#
# HOW IT WORKS:
# 1. Browser hits http://documind.local/api/health
# 2. /etc/hosts resolves documind.local → Minikube IP
# 3. NGINX Ingress Controller receives the request
# 4. Matches path /api/* → strips prefix → forwards to fastapi-service
# 5. FastAPI receives request at /health (prefix stripped!)
#
# THE rewrite-target ANNOTATION:
# Without it:  /api/health → FastAPI receives /api/health → 404!
# With it:     /api/health → FastAPI receives /health     → 200 ✅
# The $2 captures everything after the prefix via regex groups.
# ────────────────────────────────────────────────────────────────

apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: documind-ingress
  labels:
    app: documind
  annotations:
    # Strip the path prefix before forwarding to backend
    # /api/health → /health (FastAPI doesn't know about /api prefix)
    nginx.ingress.kubernetes.io/rewrite-target: /$2
    # Don't redirect HTTP to HTTPS (no TLS for local dev)
    nginx.ingress.kubernetes.io/ssl-redirect: "false"
spec:
  ingressClassName: nginx         # Use the NGINX Ingress Controller

  rules:
  - host: documind.local          # Only handle requests for this domain
    http:
      paths:
      # ── FastAPI Backend ──
      # /api/health  → fastapi-service:8000/health
      # /api/upload  → fastapi-service:8000/upload
      - path: /api(/|$)(.*)
        pathType: ImplementationSpecific
        backend:
          service:
            name: fastapi-service
            port:
              number: 8000

      # ── Qdrant Vector DB ──
      # /qdrant/healthz     → qdrant-service:6333/healthz
      # /qdrant/collections → qdrant-service:6333/collections
      - path: /qdrant(/|$)(.*)
        pathType: ImplementationSpecific
        backend:
          service:
            name: qdrant-service
            port:
              number: 6333

      # ── Neo4j Browser ──
      # /neo4j/ → neo4j-service:7474/
      - path: /neo4j(/|$)(.*)
        pathType: ImplementationSpecific
        backend:
          service:
            name: neo4j-service
            port:
              number: 7474

      # ── MinIO Console ──
      # /minio/ → minio-service:9001/
      - path: /minio(/|$)(.*)
        pathType: ImplementationSpecific
        backend:
          service:
            name: minio-service
            port:
              number: 9001
```

> **📖 Understanding the regex `(/|$)(.*)`:**
> - `(/|$)` — matches either a forward slash **or** end of string
>   - `/api/` ✅ matches — `$1` = `/`, `$2` = ``
>   - `/api/health` ✅ matches — `$1` = `/`, `$2` = `health`
>   - `/api` ✅ matches — `$1` = `` (end of string), `$2` = ``
>   - `/apifoo` ❌ doesn't match — no `/` or end after `/api`
> - `(.*)` — captures the rest of the path → goes into `$2` → becomes the rewrite target
>
> So `rewrite-target: /$2` strips the prefix and keeps only what comes after: `/api/health` → `/health`

### 4.3 Apply and Verify

```bash
# Apply the Ingress resource
kubectl apply -f k8s/base/ingress.yaml

# Check Ingress was created
kubectl get ingress
# Expected:
# NAME               CLASS   HOSTS            ADDRESS        PORTS   AGE
# documind-ingress   nginx   documind.local   192.168.49.2   80      10s

# Detailed view
kubectl describe ingress documind-ingress
# Key sections to check:
# - Rules: shows all path → service mappings
# - Annotations: rewrite-target is listed
```

> **📖 If ADDRESS is empty:** The Ingress Controller might still be processing. Wait 30 seconds and check again. On Minikube, the address should match `minikube ip`.

---

## Step 5: Test the Full Stack via Ingress

### 5.1 Test Each Service

```bash
# 1. Test FastAPI
curl http://documind.local/api/health
# Expected: {"status":"healthy","service":"documind-backend","version":"1.0.0"}

# 2. Test Qdrant
curl http://documind.local/qdrant/healthz
# Expected: ok

# 3. Test Qdrant collections
curl -s http://documind.local/qdrant/collections | python3 -m json.tool
# Expected: {"result":{"collections":[...]},"status":"ok"}

# 4. Test Neo4j (should return the Neo4j browser HTML)
curl -s http://documind.local/neo4j/ | head -5
# Expected: HTML content from Neo4j Browser

# 5. Test MinIO health
curl -s http://documind.local/minio/
# Expected: MinIO console HTML or redirect
```

> **⚠️ Neo4j Browser and MinIO Console notes:**
> These are single-page apps (SPAs) that have their own routing. The simple rewrite-target approach may not perfectly serve their static assets (JS, CSS) because they expect to be served from root `/`. For full access, you can still use `kubectl port-forward`. The Ingress approach works well for API-style access (Qdrant REST, FastAPI endpoints).
>
> In production, these UIs would each get their own subdomain (`qdrant.documind.com`, `neo4j.documind.com`) instead of path prefixes.

### 5.2 Run a Full Connectivity Check

```bash
echo "═══════════════════════════════════════════"
echo " 🌐 DocuMind Ingress Test"
echo "═══════════════════════════════════════════"

echo ""
echo "── FastAPI ──"
curl -s -o /dev/null -w "  Status: %{http_code}\n" http://documind.local/api/health

echo "── Qdrant ──"
curl -s -o /dev/null -w "  Status: %{http_code}\n" http://documind.local/qdrant/healthz

echo "── Neo4j ──"
curl -s -o /dev/null -w "  Status: %{http_code}\n" http://documind.local/neo4j/

echo "── MinIO ──"
curl -s -o /dev/null -w "  Status: %{http_code}\n" http://documind.local/minio/

echo ""
echo "═══════════════════════════════════════════"
```

**Expected output:**
```
── FastAPI ──
  Status: 200
── Qdrant ──
  Status: 200
── Neo4j ──
  Status: 200
── MinIO ──
  Status: 200 (or 302 redirect)
```

### 5.3 Convert FastAPI Service from NodePort to ClusterIP

Now that Ingress handles external access, the FastAPI Service doesn't need NodePort anymore. Update `k8s/base/fastapi-service.yaml`:

```yaml
# ─── SERVICE: DocuMind FastAPI ──────────────────────────────────
# UPDATED: Changed from NodePort to ClusterIP.
# External access is now via Ingress, not NodePort.
# ────────────────────────────────────────────────────────────────

apiVersion: v1
kind: Service
metadata:
  name: fastapi-service
  labels:
    app: fastapi
spec:
  type: ClusterIP               # Changed from NodePort!
  selector:
    app: fastapi
  ports:
  - name: http
    port: 8000
    targetPort: 8000
    protocol: TCP
  # nodePort: 30800             ← Removed! Ingress handles external access now.
```

```bash
# Apply the change
kubectl apply -f k8s/base/fastapi-service.yaml

# Verify — no more NodePort
kubectl get service fastapi-service
# Expected: TYPE=ClusterIP (not NodePort)

# Access still works via Ingress
curl http://documind.local/api/health
# Expected: 200 OK
```

> **📖 Why this matters:**
> NodePort wastes a port from the very limited 30000-32767 range and bypasses the Ingress (no centralized logging, rate limiting, or SSL). In production, **all** external traffic goes through Ingress. Internal services use ClusterIP exclusively.

---

## Step 6: Full Stack Verification

### 6.1 All Resources at a Glance

```bash
echo "═══════════════════════════════════════════"
echo " 🎯 DocuMind Kubernetes — Full Stack"
echo "═══════════════════════════════════════════"

echo ""
echo "── Deployments ──"
kubectl get deployments

echo ""
echo "── StatefulSets ──"
kubectl get statefulsets

echo ""
echo "── Pods ──"
kubectl get pods -o wide

echo ""
echo "── Services ──"
kubectl get services

echo ""
echo "── Ingress ──"
kubectl get ingress

echo ""
echo "── PVCs ──"
kubectl get pvc

echo ""
echo "── Resource Usage ──"
kubectl top pods 2>/dev/null || echo "  (enable metrics-server: minikube addons enable metrics-server)"

echo ""
echo "═══════════════════════════════════════════"
```

**Expected: 8 pods total running**
```
Deployments:   fastapi (2/2), redis (1/1), worker (1/1)
StatefulSets:  qdrant (1/1), neo4j (1/1), minio (1/1)
Total pods:    8 (2 fastapi + 1 redis + 1 worker + 1 qdrant + 1 neo4j + 1 minio)
Services:      7 (fastapi, redis, qdrant×2, neo4j×2, minio×2 headless+regular)
PVCs:          5 (redis-data, qdrant-data-qdrant-0, neo4j-data-neo4j-0, neo4j-logs-neo4j-0, minio-data-minio-0)
Ingress:       1 (documind-ingress)
```

### 6.2 Test Cross-Service Communication

```bash
# From FastAPI, verify all backend connections
kubectl exec deployment/fastapi -- python3 -c "
# Test Redis
import redis
r = redis.Redis.from_url('redis://redis-service:6379/0')
print('Redis:', 'connected' if r.ping() else 'FAILED')

# Test Qdrant
from qdrant_client import QdrantClient
q = QdrantClient(host='qdrant-service', port=6333)
print('Qdrant:', 'connected' if q.get_collections() is not None else 'FAILED')

# Test Neo4j
from neo4j import GraphDatabase
d = GraphDatabase.driver('bolt://neo4j-service:7687')
with d.session() as s:
    r = s.run('RETURN 1')
    print('Neo4j:', 'connected' if r.single()[0] == 1 else 'FAILED')
d.close()
"
```

---

## Step 7: Debugging Common Issues

### Issue 1: Ingress returns 404 for all paths

```bash
# Check Ingress Controller is running
kubectl get pods -n ingress-nginx
# Should show 1/1 Running

# Check Ingress resource
kubectl describe ingress documind-ingress
# Look for: "Default backend: default-http-backend:80 (<error: endpoints ... not found>)"

# Check NGINX Ingress Controller logs
kubectl logs -n ingress-nginx -l app.kubernetes.io/component=controller --tail=20

# Common fix: Verify ingressClassName matches
kubectl get ingressclass
# Expected: nginx   nginx   true
```

### Issue 2: `documind.local` doesn't resolve

```bash
# Verify /etc/hosts entry
cat /etc/hosts | grep documind
# Should show: 192.168.49.2  documind.local

# Verify Minikube IP hasn't changed
minikube ip
# If different from /etc/hosts, update it

# Test with IP directly
curl http://$(minikube ip)/api/health -H "Host: documind.local"
```

### Issue 3: Rewrite not working (getting /api/health instead of /health)

```bash
# Check the annotation is applied
kubectl get ingress documind-ingress -o jsonpath='{.metadata.annotations}'

# Verify the regex capture groups work
# The path pattern must be: /api(/|$)(.*)
# NOT: /api/(.*)  ← Missing the grouping

# Test directly
curl -v http://documind.local/api/health
# Check the response — if 404, the rewrite isn't stripping the prefix
```

### Issue 4: MinIO pod CrashLoopBackOff

```bash
# Check logs
kubectl logs minio-0

# Common cause: Missing secret
kubectl get secret minio-credentials
# If not found, create it:
kubectl create secret generic minio-credentials \
  --from-literal=root_user=admin \
  --from-literal=root_password=minioadmin123
```

---

## ✅ Phase 5 Checklist

### Knowledge Check
- [ ] Understand why Ingress replaces NodePort for production (L7 vs L4)
- [ ] Know the role of the Ingress Controller (NGINX pod that reads Ingress resources)
- [ ] Understand path-based routing with rewrite-target annotation
- [ ] Know how `/etc/hosts` maps local domains to cluster IPs
- [ ] Understand why ClusterIP is preferred over NodePort when Ingress exists

### Hands-On Check
```bash
# 1. Ingress Controller running
kubectl get pods -n ingress-nginx
# Expected: 1/1 Running

# 2. Ingress resource created
kubectl get ingress documind-ingress
# Expected: HOST=documind.local, ADDRESS=192.168.49.2

# 3. MinIO deployed
kubectl get statefulset minio
# Expected: READY 1/1

# 4. All 8 pods running
kubectl get pods
# Expected: 8 pods, all Running

# 5. FastAPI accessible via Ingress
curl http://documind.local/api/health
# Expected: 200 with JSON

# 6. Qdrant accessible via Ingress
curl http://documind.local/qdrant/healthz
# Expected: ok

# 7. All services are ClusterIP (no NodePort)
kubectl get services
# Expected: All ClusterIP (except kubernetes)
```

### Files Created
- [ ] `k8s/base/minio-headless-service.yaml` — MinIO Headless Service
- [ ] `k8s/base/minio-service.yaml` — MinIO ClusterIP Service
- [ ] `k8s/base/minio-statefulset.yaml` — MinIO StatefulSet with 20Gi PVC
- [ ] `k8s/base/ingress.yaml` — Ingress with path-based routing
- [ ] Updated `k8s/base/fastapi-service.yaml` — Changed NodePort → ClusterIP
- [ ] Updated `/etc/hosts` — Added `documind.local` mapping

---

## 🎓 New Concepts This Phase (Beyond Phase 4)

| Concept | What It Is | Why You Need It |
|---------|-----------|-----------------|
| **Ingress** | L7 HTTP routing rules (host/path → service) | Single entry point, path-based routing, SSL ready |
| **Ingress Controller** | Pod that reads Ingress rules and configures NGINX | Without it, Ingress resources are just inert YAML |
| **Path-Based Routing** | `/api/*` → Service A, `/qdrant/*` → Service B | One domain serves many backends |
| **Rewrite Target** | Strips path prefix before forwarding | Backend sees `/health`, not `/api/health` |
| **`/etc/hosts`** | Local DNS override | Maps `documind.local` to Minikube IP |
| **NodePort → ClusterIP** | Remove external port, route via Ingress | Cleaner, more secure, centralized access |
| **ingressClassName** | Links Ingress to specific Controller | Allows multiple Controllers in one cluster |

---

**Next up: Phase 6 — the final phase! You'll organize manifests, create deployment automation scripts, write a test suite, and document everything. This completes your Week 1 Kubernetes migration.** 🚀
