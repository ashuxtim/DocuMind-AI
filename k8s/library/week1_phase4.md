# Phase 4 — StatefulSets: Deploy Qdrant & Neo4j on Kubernetes

In Phase 3, you deployed Redis as a Deployment with a PVC — simple single-instance storage. But Qdrant (vector DB) and Neo4j (graph DB) are **real databases** that need something Deployments can't provide: **stable identity**. This is where StatefulSets come in — the most important concept you'll learn this week.

---

## Step 1: Theory — Why Deployments Don't Work for Databases

### 1.1 The Problem: Deployments Treat Pods as Disposable

Remember how Deployments work? When a pod dies, the replacement gets a **random name** and a **random IP**:

```
Deployment behavior:
  Pod dies:    fastapi-7d9c8b5f4d-abc12  (IP: 10.244.0.5)
  Replacement: fastapi-7d9c8b5f4d-xyz99  (IP: 10.244.0.9)  ← New name, new IP!
```

For FastAPI, this is fine — pods are interchangeable. But for databases, this is **dangerous**:

1. **Storage confusion:** If Pod A wrote to PVC-1 and Pod B wrote to PVC-2, which data is canonical after restart?
2. **No stable DNS:** Other services can't address a specific database instance by name
3. **Unordered startup:** Deployments start all pods simultaneously — databases need ordered init (primary first, then replicas)

### 1.2 Enter StatefulSets — Stable Everything

StatefulSets give each pod a **stable, predictable identity** that persists across restarts:

```
StatefulSet behavior:
  Pod created:  qdrant-0  (IP: 10.244.0.5)  ← Always "qdrant-0"
  Pod dies:     qdrant-0  (IP: 10.244.0.5)
  Replacement:  qdrant-0  (IP: 10.244.0.9)  ← SAME name "qdrant-0", new IP

  Scale to 2:   qdrant-0  (exists)
                qdrant-1  (created AFTER qdrant-0 is ready)  ← Ordered!

  Scale down:   qdrant-1  (deleted first)   ← Reverse order!
                qdrant-0  (kept)
```

### 1.3 StatefulSet vs Deployment — The Full Comparison

| Feature | Deployment | StatefulSet |
|---------|-----------|-------------|
| Pod names | Random hash (`fastapi-7d9c8b-abc12`) | Sequential (`qdrant-0`, `qdrant-1`) |
| Pod replacement | New random name | **Same name** (`qdrant-0` stays `qdrant-0`) |
| Storage | Shared PVC (all pods mount same volume) | **Per-pod PVC** via `volumeClaimTemplates` |
| Startup order | All pods start simultaneously | **Ordered:** 0 → 1 → 2 (waits for ready) |
| Deletion order | Random | **Reverse:** 2 → 1 → 0 |
| DNS | Via Service only | **Per-pod DNS:** `qdrant-0.qdrant-headless` |
| Use case | Stateless apps (API, workers) | **Databases, queues, clustered apps** |

> **💡 Docker Compose comparison:**
> In your `docker-compose.yml`, `neo4j` always has the hostname `neo4j` and its volume `./neo4j_data:/data` is permanently mapped. StatefulSets replicate this stability in K8s — each pod gets a permanent name and its own dedicated storage.

---

## Step 2: Theory — Headless Services: Direct Pod DNS

### 2.1 Regular Service vs Headless Service

You already know ClusterIP Services — they give you a **single virtual IP** that load-balances across pods:

```
Regular Service (ClusterIP):
  redis-service → 10.96.45.123 (virtual IP)
                   → load balances to Pod A, Pod B

  DNS: redis-service.default.svc.cluster.local → 10.96.45.123
```

A **Headless Service** (`clusterIP: None`) does something different — it returns the **actual pod IPs** directly:

```
Headless Service (clusterIP: None):
  qdrant-headless → No virtual IP!
                    → Returns pod IPs directly

  DNS: qdrant-headless.default.svc.cluster.local → 10.244.0.5, 10.244.0.6
  DNS: qdrant-0.qdrant-headless.default.svc.cluster.local → 10.244.0.5  ← Direct!
  DNS: qdrant-1.qdrant-headless.default.svc.cluster.local → 10.244.0.6  ← Direct!
```

### 2.2 Why Databases Need Both Service Types

```
┌─── Headless Service (qdrant-headless) ───────────────────┐
│  clusterIP: None                                          │
│  Purpose: Gives each pod a stable DNS name                │
│  DNS: qdrant-0.qdrant-headless → direct pod IP            │
│  Used by: StatefulSet (required), database replication     │
└───────────────────────────────────────────────────────────┘

┌─── Regular Service (qdrant-service) ─────────────────────┐
│  type: ClusterIP                                          │
│  Purpose: Single entry point for app connections          │
│  DNS: qdrant-service → virtual IP → load balances         │
│  Used by: FastAPI, Celery (they don't care which pod)     │
└───────────────────────────────────────────────────────────┘
```

> **📖 Why both?**
> - **Headless:** Required by StatefulSets for pod identity. Also used for database-to-database communication in clustered setups (primary ↔ replica).
> - **Regular ClusterIP:** What your app uses. FastAPI just calls `qdrant-service:6333` — it doesn't need to know about individual pods.

---

## Step 3: Theory — volumeClaimTemplates: Per-Pod Storage

### 3.1 The Problem with Shared PVCs

In Phase 3, Redis used a single PVC mounted by one pod. What if you scale to 2 database replicas?

```
Shared PVC (Deployment — BAD for databases):
  qdrant-abc ──┐
               ├──→ PVC: qdrant-data (10Gi)  ← BOTH write to same disk!
  qdrant-xyz ──┘                              ← Data corruption risk! 💥

Per-Pod PVC (StatefulSet — CORRECT):
  qdrant-0 ──→ PVC: qdrant-data-qdrant-0 (10Gi)  ← Own disk
  qdrant-1 ──→ PVC: qdrant-data-qdrant-1 (10Gi)  ← Own disk
```

### 3.2 How volumeClaimTemplates Work

Instead of creating PVCs manually, StatefulSets use `volumeClaimTemplates` — a **template** that auto-creates a unique PVC for each pod:

```yaml
volumeClaimTemplates:
- metadata:
    name: qdrant-data          # Template name
  spec:
    accessModes: ["ReadWriteOnce"]
    resources:
      requests:
        storage: 10Gi
```

When K8s creates `qdrant-0`, it automatically creates `qdrant-data-qdrant-0` (PVC).
When you scale to `qdrant-1`, it creates `qdrant-data-qdrant-1` (separate PVC).

> **⚠️ Important:** When you delete a StatefulSet, the PVCs are **NOT deleted**. This is a safety feature — you don't want to accidentally lose database data. You must manually delete PVCs if you want to clean up storage.

---

## Step 4: Deploy Qdrant (Day 4)

Qdrant is your vector database — it stores document embeddings for semantic search. Let's deploy it properly with a StatefulSet.

### 4.1 Create the Headless Service

Create the file `k8s/base/qdrant-headless-service.yaml`:

```yaml
# ─── HEADLESS SERVICE: Qdrant ──────────────────────────────────
# Required by StatefulSet for stable per-pod DNS.
#
# WITH THIS SERVICE:
#   qdrant-0.qdrant-headless.default.svc.cluster.local → Pod 0's IP
#   qdrant-1.qdrant-headless.default.svc.cluster.local → Pod 1's IP
#
# WHY clusterIP: None?
# Normal Services create a virtual IP. Headless Services skip that
# and return pod IPs directly via DNS. StatefulSets REQUIRE this
# for stable pod identity.
# ────────────────────────────────────────────────────────────────

apiVersion: v1
kind: Service
metadata:
  name: qdrant-headless
  labels:
    app: qdrant
spec:
  clusterIP: None              # THIS is what makes it "headless"
  selector:
    app: qdrant
  ports:
  - name: http
    port: 6333
    targetPort: 6333
    protocol: TCP
  - name: grpc
    port: 6334
    targetPort: 6334
    protocol: TCP
```

> **📖 Why two ports?**
> Qdrant exposes port `6333` for its REST API (HTTP) and `6334` for gRPC. Your FastAPI app uses the REST API. gRPC is for high-performance clients and inter-node communication in clustered mode.

### 4.2 Create the Regular Service

Create the file `k8s/base/qdrant-service.yaml`:

```yaml
# ─── SERVICE: Qdrant (Application Access) ─────────────────────
# ClusterIP Service — this is what FastAPI connects to.
# DNS: qdrant-service → load balances across Qdrant pods.
#
# WHAT THIS REPLACES from docker-compose:
#   Your docker-compose didn't expose Qdrant ports externally.
#   The backend connected via the Docker network as "qdrant:6333".
#   In K8s, it connects as "qdrant-service:6333" — same idea.
# ────────────────────────────────────────────────────────────────

apiVersion: v1
kind: Service
metadata:
  name: qdrant-service
  labels:
    app: qdrant
spec:
  type: ClusterIP
  selector:
    app: qdrant
  ports:
  - name: http
    port: 6333
    targetPort: 6333
    protocol: TCP
  - name: grpc
    port: 6334
    targetPort: 6334
    protocol: TCP
```

### 4.3 Create the StatefulSet

Create the file `k8s/base/qdrant-statefulset.yaml`:

```yaml
# ─── STATEFULSET: Qdrant Vector Database ───────────────────────
#
# WHAT THIS REPLACES from docker-compose:
#   qdrant:
#     image: qdrant/qdrant:latest
#     container_name: documind-qdrant
#     volumes:
#       - ./qdrant_storage:/qdrant/storage
#
# WHY STATEFULSET (not Deployment)?
# 1. Stable pod name: qdrant-0 (not qdrant-abc123)
# 2. Per-pod storage: each replica gets its own PVC
# 3. Ordered startup: qdrant-0 starts before qdrant-1
# 4. Required for Qdrant's clustering features
#
# WHAT'S NEW IN K8S:
# - volumeClaimTemplates auto-create 10Gi PVC per pod
# - Health checks via Qdrant's REST API
# - Resource limits prevent Qdrant from consuming all RAM
# ────────────────────────────────────────────────────────────────

apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: qdrant
  labels:
    app: qdrant
    component: database
spec:
  # ── STATEFULSET-SPECIFIC CONFIG ──
  serviceName: qdrant-headless   # MUST match the Headless Service name
                                  # This is what enables pod DNS:
                                  # qdrant-0.qdrant-headless
  replicas: 1                    # Single instance for learning
                                  # Scale to 2+ for Qdrant cluster mode

  selector:
    matchLabels:
      app: qdrant

  template:
    metadata:
      labels:
        app: qdrant
        component: database
    spec:
      containers:
      - name: qdrant
        image: qdrant/qdrant:latest
        imagePullPolicy: IfNotPresent

        ports:
        - name: http
          containerPort: 6333     # REST API
          protocol: TCP
        - name: grpc
          containerPort: 6334     # gRPC API
          protocol: TCP

        # ── VOLUME MOUNTS ──
        # Mount the auto-created PVC at Qdrant's storage directory
        volumeMounts:
        - name: qdrant-data
          mountPath: /qdrant/storage    # Qdrant's default storage path

        # ── RESOURCE LIMITS ──
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"

        # ── HEALTH CHECKS ──
        # Qdrant has a built-in healthz endpoint
        livenessProbe:
          httpGet:
            path: /healthz
            port: 6333
          initialDelaySeconds: 15
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3

        readinessProbe:
          httpGet:
            path: /healthz
            port: 6333
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 2

  # ── VOLUME CLAIM TEMPLATES ──
  # This is the StatefulSet magic — auto-creates a PVC per pod.
  # Pod qdrant-0 gets PVC "qdrant-data-qdrant-0"
  # Pod qdrant-1 would get PVC "qdrant-data-qdrant-1"
  volumeClaimTemplates:
  - metadata:
      name: qdrant-data           # Combined with pod name: qdrant-data-qdrant-0
    spec:
      accessModes:
        - ReadWriteOnce
      storageClassName: standard   # Minikube's default
      resources:
        requests:
          storage: 10Gi            # Qdrant stores vectors — needs space
```

> **📖 Key decisions explained:**
>
> **Why `serviceName: qdrant-headless`?** This field links the StatefulSet to its Headless Service. Without it, pods don't get stable DNS names. The value **must** exactly match the Headless Service's `metadata.name`.
>
> **Why 10Gi storage?** Your DocuMind app generates vector embeddings (768-dim float arrays) for every document chunk. A few hundred documents might use ~1Gi, but 10Gi gives comfortable headroom for growth.
>
> **Why `imagePullPolicy: IfNotPresent`?** Unlike your custom `documind-fastapi:v1.0` image, `qdrant/qdrant:latest` is a public Docker Hub image. But with `IfNotPresent`, K8s won't re-pull it if it's already cached in Minikube — faster pod startup.

### 4.4 Deploy Qdrant

```bash
# Apply in order: Services first, then StatefulSet
kubectl apply -f k8s/base/qdrant-headless-service.yaml
kubectl apply -f k8s/base/qdrant-service.yaml
kubectl apply -f k8s/base/qdrant-statefulset.yaml

# Watch the StatefulSet create pod qdrant-0
kubectl get pods -l app=qdrant --watch
# Expected:
# qdrant-0   0/1   Pending       0   0s
# qdrant-0   0/1   ContainerCreating   0   2s
# qdrant-0   0/1   Running       0   5s
# qdrant-0   1/1   Running       0   15s   ← Ready!
```

> **🎓 Notice the name:** The pod is called `qdrant-0` — not `qdrant-7d9c8b5f4d-abc12` like Deployment pods. This sequential naming is a StatefulSet signature.

### 4.5 Verify Qdrant

```bash
# Check the StatefulSet
kubectl get statefulset qdrant
# Expected:
# NAME     READY   AGE
# qdrant   1/1     30s

# Check the auto-created PVC
kubectl get pvc
# Expected:
# NAME                    STATUS   VOLUME        CAPACITY   ACCESS MODES   STORAGECLASS
# redis-data              Bound    pvc-xxx       1Gi        RWO            standard
# qdrant-data-qdrant-0    Bound    pvc-yyy       10Gi       RWO            standard
#                         ↑ auto-created by volumeClaimTemplate!

# Check both services
kubectl get service qdrant-headless qdrant-service
# Expected:
# NAME              TYPE        CLUSTER-IP     PORT(S)
# qdrant-headless   ClusterIP   None           6333/TCP,6334/TCP   ← No IP!
# qdrant-service    ClusterIP   10.96.x.x      6333/TCP,6334/TCP   ← Has IP

# Verify Qdrant health
kubectl exec qdrant-0 -- curl -s http://localhost:6333/healthz
# Expected: ok

# Check pod DNS resolution
kubectl run dns-test --image=busybox:1.28 --restart=Never --rm -it -- \
  nslookup qdrant-0.qdrant-headless.default.svc.cluster.local
# Expected: Name: qdrant-0.qdrant-headless... Address: 10.244.x.x
```

> **🎓 Learning moment:** Look at the Headless Service — it has `ClusterIP: None`. That's the defining characteristic. Run `kubectl get endpoints qdrant-headless` to see it pointing directly to `qdrant-0`'s IP.

### 4.6 Test Qdrant Vector Operations

```bash
# Port-forward Qdrant to your machine
kubectl port-forward svc/qdrant-service 6333:6333 &

# Create a test collection
curl -X PUT http://localhost:6333/collections/test_collection \
  -H "Content-Type: application/json" \
  -d '{
    "vectors": {
      "size": 768,
      "distance": "Cosine"
    }
  }'
# Expected: {"result":true,"status":"ok"}

# Insert a test vector
curl -X PUT http://localhost:6333/collections/test_collection/points \
  -H "Content-Type: application/json" \
  -d '{
    "points": [{
      "id": 1,
      "vector": '"$(python3 -c "import random; print([random.random() for _ in range(768)])")"',
      "payload": {"doc": "phase4-test", "source": "k8s-learning"}
    }]
  }'
# Expected: {"result":{"status":"completed"},"status":"ok"}

# Verify the collection exists
curl -s http://localhost:6333/collections/test_collection | python3 -m json.tool | head -10

# Stop port-forward
kill %1
```

### 4.7 Test Qdrant Persistence (The Key Test)

```bash
# Kill the Qdrant pod
kubectl delete pod qdrant-0

# Watch the replacement (same name!)
kubectl get pods -l app=qdrant --watch
# Expected:
# qdrant-0   0/1   Terminating   0   5m
# qdrant-0   0/1   Pending       0   0s    ← SAME NAME qdrant-0!
# qdrant-0   0/1   Running       0   3s
# qdrant-0   1/1   Running       0   15s

# Port-forward again
kubectl port-forward svc/qdrant-service 6333:6333 &

# Check if the collection survived!
curl -s http://localhost:6333/collections/test_collection | python3 -m json.tool | grep points_count
# Expected: "points_count": 1  🎉

# Stop port-forward
kill %1
```

> **🎓 The "aha" moment:** The pod died and came back with the **same name** `qdrant-0`, and it automatically remounted `qdrant-data-qdrant-0` — your test collection and vector are still there. This is the core value of StatefulSets: **stable identity + persistent per-pod storage**.

### 4.8 Test Ordered Scaling (Bonus)

```bash
# Scale Qdrant to 2 replicas
kubectl scale statefulset qdrant --replicas=2

# Watch ordered creation
kubectl get pods -l app=qdrant --watch
# Expected:
# qdrant-0   1/1   Running   0   10m   ← Already exists
# qdrant-1   0/1   Pending   0   0s    ← Created AFTER qdrant-0 is ready
# qdrant-1   0/1   Running   0   3s
# qdrant-1   1/1   Running   0   15s

# Check — now 2 PVCs exist
kubectl get pvc -l app=qdrant
# qdrant-data-qdrant-0   Bound   10Gi
# qdrant-data-qdrant-1   Bound   10Gi   ← Auto-created for qdrant-1!

# Scale back to 1
kubectl scale statefulset qdrant --replicas=1

# Watch — qdrant-1 is deleted FIRST (reverse order)
kubectl get pods -l app=qdrant --watch
# qdrant-1   1/1   Terminating   0   2m   ← Highest index removed first
# qdrant-0   1/1   Running       0   12m  ← Kept!

# Important: PVC for qdrant-1 is NOT deleted!
kubectl get pvc
# qdrant-data-qdrant-1 still exists — safety feature!
```

> **📖 Why doesn't K8s delete the PVC?** Data safety. If you scale down temporarily and scale back up, `qdrant-1` will remount its **existing** PVC with all the data intact. To actually delete the PVC, you must do it manually: `kubectl delete pvc qdrant-data-qdrant-1`.

---

## Step 5: Deploy Neo4j (Day 5)

Neo4j is your graph database — it stores the knowledge graph of document relationships. It needs **two volumes** (data + logs) and specific environment configuration.

### 5.1 Create the Headless Service

Create the file `k8s/base/neo4j-headless-service.yaml`:

```yaml
# ─── HEADLESS SERVICE: Neo4j ──────────────────────────────────
# Required by StatefulSet for stable pod DNS.
# DNS: neo4j-0.neo4j-headless.default.svc.cluster.local
# ────────────────────────────────────────────────────────────────

apiVersion: v1
kind: Service
metadata:
  name: neo4j-headless
  labels:
    app: neo4j
spec:
  clusterIP: None
  selector:
    app: neo4j
  ports:
  - name: bolt                   # Bolt protocol — what your Python driver uses
    port: 7687
    targetPort: 7687
    protocol: TCP
  - name: http                   # HTTP — Neo4j Browser UI
    port: 7474
    targetPort: 7474
    protocol: TCP
```

> **📖 Neo4j's two ports:**
> - `7687` (Bolt): The binary protocol used by the Python `neo4j` driver. This is what `bolt://neo4j-service:7687` connects to.
> - `7474` (HTTP): The Neo4j Browser — a web UI for running Cypher queries visually.

### 5.2 Create the Regular Service

Create the file `k8s/base/neo4j-service.yaml`:

```yaml
# ─── SERVICE: Neo4j (Application Access) ──────────────────────
# ClusterIP Service for application connections.
# FastAPI connects to "neo4j-service:7687" (Bolt protocol).
#
# WHAT THIS REPLACES from docker-compose:
#   The backend connected to neo4j as "neo4j:7687" via Docker network.
#   In K8s, it's "neo4j-service:7687" — matches your ConfigMap.
# ────────────────────────────────────────────────────────────────

apiVersion: v1
kind: Service
metadata:
  name: neo4j-service
  labels:
    app: neo4j
spec:
  type: ClusterIP
  selector:
    app: neo4j
  ports:
  - name: bolt
    port: 7687
    targetPort: 7687
    protocol: TCP
  - name: http
    port: 7474
    targetPort: 7474
    protocol: TCP
```

### 5.3 Create the StatefulSet

Create the file `k8s/base/neo4j-statefulset.yaml`:

```yaml
# ─── STATEFULSET: Neo4j Graph Database ─────────────────────────
#
# WHAT THIS REPLACES from docker-compose:
#   neo4j:
#     image: neo4j:latest
#     container_name: documind-graph
#     environment:
#       - NEO4J_AUTH=${NEO4J_USER:-neo4j}/${NEO4J_PASSWORD:-password}
#     volumes:
#       - ./neo4j_data:/data
#
# KEY DIFFERENCES IN K8S:
# - TWO PVCs: data (10Gi) + logs (1Gi) — separated for management
# - Credentials from K8s Secret (not .env file)
# - JVM heap + page cache tuning via environment variables
# - Health checks via Neo4j's built-in HTTP endpoints
#
# ⚠️ K8S GOTCHA (what broke the first deploy):
# K8s auto-injects env vars for every Service in the namespace.
# Because the Service is named "neo4j-service", K8s creates vars like:
#   NEO4J_SERVICE_PORT_7687_TCP_PROTO=tcp
# Neo4j sees anything starting with "NEO4J_" and tries to parse it
# as config → "Unrecognized setting" → crash.
# FIX: Set server.config.strict_validation.enabled=false
# ────────────────────────────────────────────────────────────────

apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: neo4j
  labels:
    app: neo4j
    component: database
spec:
  serviceName: neo4j-headless    # Links to Headless Service
  replicas: 1                    # Single instance — Community Edition
                                  # (Enterprise Edition supports clustering)
  selector:
    matchLabels:
      app: neo4j

  template:
    metadata:
      labels:
        app: neo4j
        component: database
    spec:
      containers:
      - name: neo4j
        image: neo4j:latest
        imagePullPolicy: IfNotPresent

        ports:
        - name: bolt
          containerPort: 7687     # Bolt protocol — Python driver connects here
          protocol: TCP
        - name: http
          containerPort: 7474     # HTTP — Neo4j Browser UI
          protocol: TCP

        # ── ENVIRONMENT VARIABLES ──
        env:
        # Disable auth for local development.
        # For production, change to: "neo4j/your-secure-password"
        - name: NEO4J_AUTH
          value: "none"

        # ── K8s COMPATIBILITY FIX ──
        # K8s injects Service env vars (like NEO4J_SERVICE_PORT_7687_TCP_PROTO)
        # into every pod. Neo4j sees "NEO4J_*" and tries to parse them as
        # config settings → "Unrecognized setting" → crash!
        # This tells Neo4j to ignore settings it doesn't recognize.
        - name: NEO4J_server_config_strict__validation_enabled
          value: "false"

        # ── JVM TUNING ──
        # Neo4j runs on the JVM — these control memory allocation.
        # Double underscores (__) map to dashes in Neo4j config:
        #   server.memory.heap.max_size → NEO4J_server_memory_heap_max__size
        - name: NEO4J_server_memory_heap_initial__size
          value: "256m"           # Initial JVM heap
        - name: NEO4J_server_memory_heap_max__size
          value: "512m"           # Max JVM heap (must fit within container limits)
        - name: NEO4J_server_memory_pagecache_size
          value: "256m"           # Off-heap cache for graph data pages

        # ── VOLUME MOUNTS ──
        volumeMounts:
        - name: neo4j-data
          mountPath: /data         # Neo4j's database files
        - name: neo4j-logs
          mountPath: /logs         # Neo4j's transaction logs

        # ── RESOURCE LIMITS ──
        # Neo4j JVM needs heap (512m) + page cache (256m) + overhead
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "1536Mi"       # 1.5Gi — allows heap + pagecache + OS overhead
            cpu: "1000m"

        # ── HEALTH CHECKS ──
        livenessProbe:
          httpGet:
            path: /                # Neo4j returns 200 on root when alive
            port: 7474
          initialDelaySeconds: 60  # Neo4j takes ~30-60s to start (JVM warmup)
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 5     # More lenient — Neo4j startup is slow

        readinessProbe:
          httpGet:
            path: /                # Returns 200 when ready for queries
            port: 7474
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3

  # ── VOLUME CLAIM TEMPLATES ──
  # Two separate PVCs per pod: data + logs
  # Pod neo4j-0 gets: neo4j-data-neo4j-0 + neo4j-logs-neo4j-0
  volumeClaimTemplates:
  - metadata:
      name: neo4j-data
    spec:
      accessModes:
        - ReadWriteOnce
      storageClassName: standard
      resources:
        requests:
          storage: 10Gi           # Graph data — grows with relationships

  - metadata:
      name: neo4j-logs
    spec:
      accessModes:
        - ReadWriteOnce
      storageClassName: standard
      resources:
        requests:
          storage: 1Gi            # Transaction logs — rotate frequently
```

> **📖 Key decisions explained:**
>
> **Why two PVCs?** Separating data and logs is a database best practice:
> - **Data PVC (`/data`):** Contains the actual graph — high value, needs backup
> - **Logs PVC (`/logs`):** Transaction logs — helpful for debugging but can be rotated
> - In production, you'd use different storage classes (fast SSD for data, cheaper disk for logs)
>
> **Why `initialDelaySeconds: 60`?** Neo4j's JVM needs time to start. It loads indexes, warms the page cache, and runs recovery on startup. Killing it before completion causes a restart loop (`CrashLoopBackOff`).
>
> **Why `NEO4J_AUTH: none`?** For local learning, auth adds friction. Every Cypher query would need credentials. You can always enable it later by changing this to `neo4j/password`.
>
> **Why `NEO4J_server_memory_heap_max__size` uses double underscores?** Neo4j maps env vars to config via this pattern: dots become `_`, dashes become `__`. So `server.memory.heap.max_size` becomes `NEO4J_server_memory_heap_max__size`.

### 5.4 Deploy Neo4j

```bash
# Apply Services first, then StatefulSet
kubectl apply -f k8s/base/neo4j-headless-service.yaml
kubectl apply -f k8s/base/neo4j-service.yaml
kubectl apply -f k8s/base/neo4j-statefulset.yaml

# Watch — Neo4j takes longer to start than Qdrant
kubectl get pods -l app=neo4j --watch
# Expected (be patient — ~60s to ready):
# neo4j-0   0/1   Pending             0   0s
# neo4j-0   0/1   ContainerCreating   0   2s
# neo4j-0   0/1   Running             0   5s
# neo4j-0   1/1   Running             0   60s   ← Ready! (slow due to JVM)
```

### 5.5 Verify Neo4j

```bash
# Check StatefulSet
kubectl get statefulset neo4j
# Expected: READY 1/1

# Check PVCs — you should now see 4 PVCs total
kubectl get pvc
# Expected:
# NAME                    STATUS   CAPACITY   STORAGECLASS
# redis-data              Bound    1Gi        standard
# qdrant-data-qdrant-0    Bound    10Gi       standard
# neo4j-data-neo4j-0      Bound    10Gi       standard     ← NEW
# neo4j-logs-neo4j-0      Bound    1Gi        standard     ← NEW

# Check Neo4j logs
kubectl logs neo4j-0 --tail=10
# Look for: "Started."  or "Remote interface available at http://localhost:7474/"

# Quick health check
kubectl exec neo4j-0 -- curl -s http://localhost:7474/ | head -5
```

### 5.6 Test Neo4j with Cypher Queries

```bash
# Run a Cypher query via cypher-shell (built into the Neo4j image)
kubectl exec -it neo4j-0 -- cypher-shell -u neo4j -p none "RETURN 'Hello from K8s!' AS message"
# If auth is disabled, use:
kubectl exec -it neo4j-0 -- cypher-shell "RETURN 'Hello from K8s!' AS message"
# Expected:
# +-------------------------+
# | message                 |
# +-------------------------+
# | "Hello from K8s!"       |
# +-------------------------+

# Create some test data
kubectl exec -it neo4j-0 -- cypher-shell "
CREATE (d:Document {name: 'k8s-phase4-test', type: 'pdf'})
CREATE (c:Chunk {text: 'StatefulSets provide stable identity', index: 0})
CREATE (d)-[:HAS_CHUNK]->(c)
RETURN d.name, c.text
"
# Expected: k8s-phase4-test | StatefulSets provide stable identity

# Verify data
kubectl exec -it neo4j-0 -- cypher-shell "MATCH (n) RETURN count(n) AS nodeCount"
# Expected: nodeCount = 2
```

### 5.7 Test Neo4j Persistence

```bash
# Kill the Neo4j pod
kubectl delete pod neo4j-0

# Watch — same name qdrant-0, same PVCs
kubectl get pods -l app=neo4j --watch
# Wait for neo4j-0 to be 1/1 Running (takes ~60s)

# Verify data survived!
kubectl exec -it neo4j-0 -- cypher-shell "MATCH (n) RETURN count(n) AS nodeCount"
# Expected: nodeCount = 2  🎉

# Check the specific test data
kubectl exec -it neo4j-0 -- cypher-shell "
MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk)
RETURN d.name, c.text
"
# Expected: k8s-phase4-test | StatefulSets provide stable identity
```

### 5.8 Access Neo4j Browser (Optional)

```bash
# Port-forward the HTTP port
kubectl port-forward svc/neo4j-service 7474:7474 7687:7687 &

# Open in your browser: http://localhost:7474
# Connect with: bolt://localhost:7687  (no auth if NEO4J_AUTH=none)
# Try running: MATCH (n) RETURN n
# You'll see your test nodes visually!

# Stop port-forward
kill %1
```

---

## Step 6: Integrate Databases with FastAPI

### 6.1 Restart FastAPI to pick up live databases

```bash
# Restart FastAPI pods so they reconnect to the now-live databases
kubectl rollout restart deployment fastapi

# Wait for pods to be ready
kubectl get pods -l app=fastapi --watch

# Check logs — look for successful connections
kubectl logs -l app=fastapi --tail=20
```

**What to look for:**
```
✅ StateManager connected to Redis
✅ Neo4j connected: bolt://neo4j-service:7687       ← NEW!
✅ Qdrant connected: qdrant-service:6333             ← NEW!
⚠️ Ollama not available (not deployed yet)           ← Expected
```

### 6.2 Test from FastAPI pod

```bash
# Test Qdrant connectivity from FastAPI
kubectl exec deployment/fastapi -- python3 -c "
from qdrant_client import QdrantClient
client = QdrantClient(host='qdrant-service', port=6333)
collections = client.get_collections()
print('Qdrant collections:', collections)
"

# Test Neo4j connectivity from FastAPI
kubectl exec deployment/fastapi -- python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://neo4j-service:7687')
with driver.session() as session:
    result = session.run('RETURN 1 AS num')
    print('Neo4j test:', result.single()['num'])
driver.close()
"
```

### 6.3 Also restart the worker

```bash
kubectl rollout restart deployment worker

# Verify worker can reach all services
kubectl logs -l app=worker --tail=10
```

---

## Step 7: Create a Neo4j Backup Script (Bonus)

Create the file `k8s/scripts/backup-neo4j.sh`:

```bash
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
```

```bash
chmod +x k8s/scripts/backup-neo4j.sh
```

> **📖 Note:** Neo4j Community Edition requires the database to be stopped for a consistent dump. In production with Enterprise Edition, you'd use online backup. For learning purposes, this script demonstrates the concept.

---

## Step 8: Full Stack Status Check

### 8.1 Run the status script

```bash
./k8s/scripts/k8s-status.sh
```

**Expected output:**
```
═══════════════════════════════════════════
 🎯 DocuMind Kubernetes Status
═══════════════════════════════════════════

── Deployments ──────────────────────────
NAME      READY   UP-TO-DATE   AVAILABLE   AGE
fastapi   2/2     2            2           2d
redis     1/1     1            1           1d
worker    1/1     1            1           1d

── StatefulSets ─────────────────────────
NAME     READY   AGE
qdrant   1/1     1h
neo4j    1/1     30m

── Pods ─────────────────────────────────
NAME                       READY   STATUS    RESTARTS   AGE
fastapi-xxx                1/1     Running   0          10m
fastapi-yyy                1/1     Running   0          10m
redis-zzz                  1/1     Running   0          1d
worker-aaa                 1/1     Running   0          10m
qdrant-0                   1/1     Running   0          1h
neo4j-0                    1/1     Running   0          30m

── Services ─────────────────────────────
NAME              TYPE        CLUSTER-IP      PORT(S)
fastapi-service   NodePort    10.96.x.x       8000:30800/TCP
redis-service     ClusterIP   10.96.x.x       6379/TCP
qdrant-headless   ClusterIP   None            6333/TCP,6334/TCP
qdrant-service    ClusterIP   10.96.x.x       6333/TCP,6334/TCP
neo4j-headless    ClusterIP   None            7687/TCP,7474/TCP
neo4j-service     ClusterIP   10.96.x.x       7687/TCP,7474/TCP

── PVCs ─────────────────────────────────
NAME                   STATUS   CAPACITY   STORAGECLASS
redis-data             Bound    1Gi        standard
qdrant-data-qdrant-0   Bound    10Gi       standard
neo4j-data-neo4j-0     Bound    10Gi       standard
neo4j-logs-neo4j-0     Bound    1Gi        standard
```

### 8.2 Update the status script

Add StatefulSet and PVC sections to your `k8s/scripts/k8s-status.sh`:

```bash
# Add these sections after the Deployments section:

echo ""
echo "── StatefulSets ─────────────────────────"
kubectl get statefulsets

echo ""
echo "── PersistentVolumeClaims ─────────────────"
kubectl get pvc
```

---

## Step 9: Debugging Common Issues

### Issue 1: StatefulSet pod stuck in Pending

```bash
# Symptom
kubectl get pods -l app=qdrant
# qdrant-0   0/1   Pending   0   5m

# Diagnosis
kubectl describe pod qdrant-0
# Events: "pod has unbound immediate PersistentVolumeClaims"

# Fix: Check if StorageClass can provision
kubectl get storageclass
kubectl get pvc
# If PVC stuck in Pending:
minikube addons enable default-storageclass
minikube addons enable storage-provisioner
```

### Issue 2: Neo4j CrashLoopBackOff

```bash
# Symptom: Neo4j keeps restarting
kubectl get pods -l app=neo4j
# neo4j-0   0/1   CrashLoopBackOff   5   10m

# Diagnosis: Check logs from previous crash
kubectl logs neo4j-0 --previous

# Common causes:
# 1. Not enough memory → Increase limits to 2Gi
# 2. liveness probe fires too early → Increase initialDelaySeconds to 90
# 3. Corrupted data volume → Delete PVC and recreate:
kubectl delete statefulset neo4j
kubectl delete pvc neo4j-data-neo4j-0 neo4j-logs-neo4j-0
kubectl apply -f k8s/base/neo4j-statefulset.yaml
```

### Issue 3: FastAPI can't connect to databases

```bash
# Check 1: Are the database pods running?
kubectl get pods -l component=database
# All should be 1/1 Running

# Check 2: Do Services have endpoints?
kubectl get endpoints qdrant-service neo4j-service
# Both should list pod IPs

# Check 3: DNS resolution from FastAPI pod
kubectl exec deployment/fastapi -- nslookup qdrant-service
kubectl exec deployment/fastapi -- nslookup neo4j-service

# Check 4: Direct connectivity
kubectl exec deployment/fastapi -- curl -s http://qdrant-service:6333/healthz
kubectl exec deployment/fastapi -- curl -s http://neo4j-service:7474/
```

### Issue 4: PVCs not deleted after StatefulSet deletion

```bash
# This is BY DESIGN — safety feature!
# To clean up orphaned PVCs:
kubectl get pvc
kubectl delete pvc qdrant-data-qdrant-1   # Only if you're sure!

# To delete ALL PVCs for a StatefulSet:
kubectl delete pvc -l app=qdrant
```

---

## ✅ Phase 4 Checklist

### Knowledge Check
- [ ] Can explain why databases need StatefulSets instead of Deployments
- [ ] Understand stable pod identity: `qdrant-0` is always `qdrant-0` after restart
- [ ] Know the difference between Headless Service (`clusterIP: None`) and regular ClusterIP
- [ ] Understand `volumeClaimTemplates` — auto-creates per-pod PVCs
- [ ] Know that PVCs persist even after StatefulSet deletion (safety feature)
- [ ] Can explain ordered pod lifecycle: create 0→1→2, delete 2→1→0

### Hands-On Check
```bash
# 1. Both StatefulSets running
kubectl get statefulset qdrant neo4j
# Expected: Both show READY 1/1

# 2. Pod names are sequential (not random hashes)
kubectl get pods -l component=database
# Expected: qdrant-0, neo4j-0 (no random suffixes!)

# 3. PVCs auto-created by volumeClaimTemplates
kubectl get pvc
# Expected: qdrant-data-qdrant-0, neo4j-data-neo4j-0, neo4j-logs-neo4j-0

# 4. Qdrant health check
kubectl exec qdrant-0 -- curl -s http://localhost:6333/healthz
# Expected: ok

# 5. Neo4j accessible
kubectl exec neo4j-0 -- cypher-shell "RETURN 1 AS test"
# Expected: test = 1

# 6. Data survives pod deletion (Qdrant)
kubectl exec qdrant-0 -- curl -s http://localhost:6333/collections | grep test_collection
kubectl delete pod qdrant-0
sleep 20
kubectl exec qdrant-0 -- curl -s http://localhost:6333/collections | grep test_collection
# Expected: test_collection exists in both checks

# 7. FastAPI can connect to both
kubectl exec deployment/fastapi -- curl -s http://qdrant-service:6333/healthz
kubectl exec deployment/fastapi -- curl -s http://neo4j-service:7474/
# Expected: Both return success
```

### Files Created
- [ ] `k8s/base/qdrant-headless-service.yaml` — Headless Service for StatefulSet DNS
- [ ] `k8s/base/qdrant-service.yaml` — ClusterIP Service for app connections
- [ ] `k8s/base/qdrant-statefulset.yaml` — Qdrant StatefulSet with 10Gi VCT
- [ ] `k8s/base/neo4j-headless-service.yaml` — Headless Service for StatefulSet DNS
- [ ] `k8s/base/neo4j-service.yaml` — ClusterIP Service for app connections
- [ ] `k8s/base/neo4j-statefulset.yaml` — Neo4j StatefulSet with data (10Gi) + logs (1Gi) VCTs
- [ ] `k8s/scripts/backup-neo4j.sh` — Database backup script
- [ ] Updated `k8s/scripts/k8s-status.sh` — Added StatefulSet and PVC sections

---

## 🎓 New Concepts This Phase (Beyond Phase 3)

| Concept | What It Is | Why You Need It |
|---------|-----------|-----------------|
| **StatefulSet** | Workload controller with stable pod identity | Databases need predictable names and ordered lifecycle |
| **Headless Service** | Service with `clusterIP: None` | Enables per-pod DNS (`qdrant-0.qdrant-headless`) |
| **volumeClaimTemplates** | Auto-creates PVC per pod | Each database replica gets its own dedicated storage |
| **Ordered Pod Lifecycle** | Pods create 0→1→2, delete 2→1→0 | Safe for databases — primary starts first |
| **Stable Identity** | Pod name survives restarts | `qdrant-0` is always `qdrant-0`, remounts same PVC |
| **PVC Retention** | PVCs persist after StatefulSet deletion | Safety feature — prevents accidental data loss |
| **Per-Pod DNS** | `pod-name.headless-service` resolves directly | Enables direct pod-to-pod communication for clustering |
| **Multi-Volume StatefulSet** | Multiple VCTs per StatefulSet | Separate data and logs onto different volumes |

---

**Next up: Phase 5 — Ingress & Full Stack Networking. You'll deploy MinIO for object storage, set up an NGINX Ingress Controller for path-based routing, and access all services through a single `documind.local` domain.** 🚀
