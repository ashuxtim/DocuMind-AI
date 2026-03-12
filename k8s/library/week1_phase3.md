# Phase 3 — ConfigMaps, Secrets & Redis: Externalizing Configuration

In Phase 2, you hardcoded environment variables directly into the Deployment YAML. That works, but it's the equivalent of putting passwords in your source code — messy, insecure, and impossible to manage across environments. Now you'll learn how K8s separates **configuration** from **code**, deploy **Redis** with persistent storage, and connect your **Celery worker**.

---

## Step 1: Theory — ConfigMaps: Externalizing Configuration

### 1.1 The Problem You Saw in Phase 2

Look at your `fastapi-deployment.yaml` right now:

```yaml
env:
- name: NEO4J_PASSWORD
  value: "password"             # ⚠️ Password in plain text, in version control!
- name: REDIS_URL
  value: "redis://redis-service:6379/0"  # Config mixed with deployment spec
- name: QDRANT_HOST
  value: "qdrant-service"       # Same config repeated if workers need it too
```

**Three problems:**
1. **Secrets in plain text** — anyone with access to your YAML can see `NEO4J_PASSWORD`
2. **Config duplication** — when Celery workers need the same `REDIS_URL`, you'd copy-paste it
3. **No environment separation** — can't easily change values for dev vs staging vs production

### 1.2 ConfigMaps — The Non-Sensitive Config Store

A ConfigMap is a K8s object that stores **non-sensitive** key-value pairs. Pods reference them instead of hardcoding values.

```
Without ConfigMap:
  ┌─── Deployment YAML ───┐
  │ env:                    │
  │   REDIS_URL: redis://.. │  ← Hardcoded per deployment
  │   QDRANT_HOST: qdrant.. │
  └─────────────────────────┘

With ConfigMap:
  ┌─── ConfigMap ──────────────┐
  │ REDIS_URL: redis://..       │  ← Single source of truth
  │ QDRANT_HOST: qdrant-service │
  │ QDRANT_PORT: "6333"         │
  │ LLM_PROVIDER: ollama        │
  └─────────────────────────────┘
       ↑               ↑
  FastAPI Deployment   Worker Deployment
  (references it)      (references same config!)
```

> **📖 Docker Compose comparison:**
> Your `.env` file in Compose is the closest equivalent — a shared config file that multiple services reference via `env_file: .env`. ConfigMaps are that concept, but managed by K8s, versioned, and mountable as files too.

### 1.3 What Goes in a ConfigMap vs What Doesn't

| Data | ConfigMap? | Why |
|------|-----------|-----|
| `REDIS_URL=redis://redis-service:6379/0` | ✅ Yes | Service endpoint, not sensitive |
| `QDRANT_HOST=qdrant-service` | ✅ Yes | Service endpoint |
| `LLM_PROVIDER=ollama` | ✅ Yes | Behavioral config |
| `NEO4J_PASSWORD=password` | ❌ No | **Secret!** Use K8s Secret instead |
| `LANGCHAIN_API_KEY=lsv2_pt_...` | ❌ No | **API key!** Use Secret |

---

## Step 2: Theory — Secrets: Protecting Sensitive Data

### 2.1 Secrets — Like ConfigMaps, But Encrypted at Rest

K8s Secrets store sensitive data (passwords, API keys, tokens). They look similar to ConfigMaps but with key differences:

| Feature | ConfigMap | Secret |
|---------|-----------|--------|
| Data encoding | Plain text | Base64 encoded |
| Stored in etcd | As-is | Encrypted at rest (if enabled) |
| RBAC access | Anyone with namespace access | Can be restricted separately |
| Use case | Service URLs, feature flags | Passwords, API keys, TLS certs |

```
┌─── Secret ───────────────────────────────┐
│ NEO4J_PASSWORD: cGFzc3dvcmQ=              │  ← Base64 of "password"
│ LANGCHAIN_API_KEY: bHN2Ml9wdF8z...        │  ← Base64 of the actual key
│ LLAMA_CLOUD_API_KEY: bGx4LVBTUkdJ...     │
└───────────────────────────────────────────┘
```

> **⚠️ Important caveat:** Base64 is **NOT** encryption — it's encoding. Anyone who can `kubectl get secret` can decode it. In production, you'd use:
> - **Sealed Secrets** (encrypted Secrets stored in Git)
> - **External secret stores** (HashiCorp Vault, AWS Secrets Manager)
> - **etcd encryption at rest** 
>
> For learning on Minikube, plain Secrets are fine.

### 2.2 Creating Secrets — Two Methods

**Method 1: Imperative (quick, not in version control)**
```bash
kubectl create secret generic my-secret --from-literal=password=mypass
```

**Method 2: Declarative (YAML, but you must base64-encode values)**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: my-secret
type: Opaque
data:
  password: bXlwYXNz    # base64 of "mypass"
```

> **📖 Pro tip:** You can use `stringData` instead of `data` to avoid manual base64 encoding:
> ```yaml
> stringData:
>   password: mypass    # K8s auto-encodes to base64
> ```

---

## Step 3: Theory — PersistentVolumes: Data That Survives Pod Restarts

### 3.1 The Problem: Containers Are Ephemeral

When a pod dies, everything inside it is **gone**. Redis stores your Celery task states in memory and on disk — if the Redis pod restarts without persistent storage, **all task state is lost**.

```
Without PV:
  Pod restarts → Container filesystem wiped → Redis data GONE 💀

With PV:
  Pod restarts → Container filesystem wiped → BUT volume is still there → Redis remounts it → Data intact ✅
```

### 3.2 The Three-Object Model

K8s storage uses three objects that work together:

```
┌────────────────────────────────────────────────────────────┐
│                    STORAGE ARCHITECTURE                      │
│                                                              │
│  PersistentVolume (PV)           PersistentVolumeClaim (PVC)│
│  ────────────────────            ───────────────────────── │
│  "Here's 10Gi of disk"          "I need 2Gi of disk"       │
│  (Cluster admin creates)        (Developer creates)         │
│          ↕ K8s matches them ↕                                │
│                                                              │
│  Pod                                                         │
│  ───                                                         │
│  "Mount the PVC at /data"                                   │
│                                                              │
│  ┌─── Container ──────┐    ┌─── PVC: redis-data ──┐        │
│  │  Redis process      │    │  2Gi SSD             │        │
│  │  /data ────────────────→ │  ReadWriteOnce       │        │
│  └─────────────────────┘    └──────────────────────┘        │
└────────────────────────────────────────────────────────────┘
```

> **💡 Docker Compose comparison:**
> In your `docker-compose.yml`, you have `volumes: - ./neo4j_data:/data`. That's a **bind mount** — it maps a host folder into the container. K8s PVCs are the same concept, but cluster-managed: K8s handles provisioning, lifecycle, and can even resize volumes.

### 3.3 Storage Classes — Minikube vs Cloud

| Environment | Default StorageClass | What It Does |
|-------------|---------------------|--------------|
| **Minikube** | `standard` | Creates folders on the Minikube node |
| **AWS EKS** | `gp3` | Provisions EBS SSD volumes |
| **GKE** | `standard` | Provisions GCE Persistent Disks |

In Minikube, you don't need to create PVs manually — the `standard` StorageClass **auto-provisions** them when you create a PVC. This is called **dynamic provisioning**.

---

## Step 4: Create the ConfigMap

Now let's build the actual K8s objects. Start with the ConfigMap for all non-sensitive configuration.

### 4.1 Create the ConfigMap YAML

Create the file `k8s/base/documind-configmap.yaml`:

```yaml
# ─── CONFIGMAP: DocuMind Shared Configuration ──────────────────
# Stores non-sensitive config shared across FastAPI and Celery.
#
# WHAT THIS REPLACES:
# The hardcoded 'env:' values in fastapi-deployment.yaml AND
# the .env file from docker-compose.
#
# WHY IT'S BETTER:
# - Single source of truth (change once, all pods pick it up)
# - Can be updated without rebuilding Docker images
# - K8s tracks revision history
# ────────────────────────────────────────────────────────────────

apiVersion: v1
kind: ConfigMap
metadata:
  name: documind-config
  labels:
    app: documind
data:
  # ── Service Discovery (K8s DNS names) ──
  # These match the Service names you'll create for each database.
  # In K8s, "redis-service" resolves to the ClusterIP of the Redis Service.
  REDIS_URL: "redis://redis-service:6379/0"
  NEO4J_URI: "bolt://neo4j-service:7687"
  NEO4J_USER: "neo4j"
  QDRANT_HOST: "qdrant-service"
  QDRANT_PORT: "6333"
  OLLAMA_BASE_URL: "http://ollama-service:11434"

  # ── Application Config ──
  LLM_PROVIDER: "ollama"
  UPLOAD_FOLDER: "./uploads"

  # ── Observability ──
  LANGCHAIN_TRACING_V2: "true"
  LANGCHAIN_ENDPOINT: "https://api.smith.langchain.com"
  LANGCHAIN_PROJECT: "DocuMind_K8s"
```

> **📖 Key decisions:**
> 
> **Why `QDRANT_PORT` is a string `"6333"`?** ConfigMap values are **always strings**. Even if they look like numbers, K8s stores them as strings. Your Python code calls `int(os.getenv("QDRANT_PORT", 6333))` which handles the conversion.
>
> **Why `NEO4J_USER` is here, not in the Secret?** The username isn't sensitive — it's the same across all environments. Only the password is secret.
>
> **Why did `LANGCHAIN_PROJECT` change?** You're now running in K8s, so a different project name helps you distinguish K8s traces from Docker Compose traces in LangSmith.

### 4.2 Apply and verify

```bash
# Apply the ConfigMap
kubectl apply -f k8s/base/documind-configmap.yaml

# Verify it exists
kubectl get configmaps
# Expected: documind-config   3      5s

# Inspect the data
kubectl describe configmap documind-config
# You'll see all your key-value pairs listed
```

---

## Step 5: Create the Secret

### 5.1 Create the Secret YAML

Create the file `k8s/base/documind-secret.yaml`:

```yaml
# ─── SECRET: DocuMind Sensitive Configuration ──────────────────
# Stores passwords, API keys, and tokens.
#
# ⚠️ WARNING: Do NOT commit this file to Git!
# Add 'k8s/base/documind-secret.yaml' to your .gitignore.
#
# In production, use Sealed Secrets or an external secret store.
# ────────────────────────────────────────────────────────────────

apiVersion: v1
kind: Secret
metadata:
  name: documind-secrets
  labels:
    app: documind
type: Opaque

# stringData lets you write plain text — K8s auto-encodes to Base64
# This is easier than manually running `echo -n "password" | base64`
stringData:
  NEO4J_PASSWORD: "password"
  LANGCHAIN_API_KEY: "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"
  LLAMA_CLOUD_API_KEY: "llx-PSRGIvyvpqiCaFtKysSnAjo5lYjLq7NrljEomJRZCaRN13vX"
  # Add your API keys if you use them:
  # OPENAI_API_KEY: "sk-..."
  # GOOGLE_API_KEY: "AIza..."
```

> **📖 Why `stringData` instead of `data`?**
> - `data:` requires base64-encoded values (e.g., `cGFzc3dvcmQ=`)
> - `stringData:` accepts plain text and K8s encodes it for you
> - Both produce the same internal representation
> - `stringData` is easier for local development; in production, you'd use `data` with values from a CI pipeline

### 5.2 Add to .gitignore

**This is critical** — never commit secrets to Git:

```bash
echo "k8s/base/documind-secret.yaml" >> .gitignore
```

### 5.3 Apply and verify

```bash
# Apply
kubectl apply -f k8s/base/documind-secret.yaml

# Verify (notice it doesn't show the actual values!)
kubectl get secrets
# Expected: documind-secrets   Opaque   3      5s

# Peek at a value (base64 encoded)
kubectl get secret documind-secrets -o jsonpath='{.data.NEO4J_PASSWORD}' | base64 -d
# Expected: password
```

> **🎓 Learning moment:** Try `kubectl get secret documind-secrets -o yaml` — you'll see the values are base64-encoded, not plain text. This is why Secrets have a thin security layer over ConfigMaps. But remember: base64 ≠ encryption!

---

## Step 6: Refactor FastAPI Deployment to Use ConfigMap & Secret

Now replace the hardcoded `env:` block in your FastAPI Deployment with references to the ConfigMap and Secret.

### 6.1 Update `k8s/base/fastapi-deployment.yaml`

Replace the entire `env:` section (lines with hardcoded values) with `envFrom`:

```yaml
# ─── DEPLOYMENT: DocuMind FastAPI Backend ───────────────────────
# UPDATED: Now uses ConfigMap and Secret instead of hardcoded env vars.
# ────────────────────────────────────────────────────────────────

apiVersion: apps/v1
kind: Deployment
metadata:
  name: fastapi
  labels:
    app: fastapi
    component: backend
spec:
  replicas: 2
  selector:
    matchLabels:
      app: fastapi
  template:
    metadata:
      labels:
        app: fastapi
        component: backend
    spec:
      containers:
      - name: fastapi
        image: documind-fastapi:v1.1
        imagePullPolicy: IfNotPresent

        ports:
        - name: http
          containerPort: 8000
          protocol: TCP

        # ── ENVIRONMENT FROM CONFIGMAP & SECRET ──
        # envFrom injects ALL keys from the ConfigMap/Secret as env vars.
        # This replaces the manual "env:" list from Phase 2.
        #
        # BEFORE (Phase 2):
        #   env:
        #     - name: REDIS_URL
        #       value: "redis://redis-service:6379/0"  ← Hardcoded
        #
        # AFTER (Phase 3):
        #   envFrom:
        #     - configMapRef: documind-config  ← All keys become env vars
        envFrom:
        - configMapRef:
            name: documind-config      # Injects: REDIS_URL, QDRANT_HOST, etc.
        - secretRef:
            name: documind-secrets     # Injects: NEO4J_PASSWORD, API keys

        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"

        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3

        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 2
```

> **📖 The `envFrom` pattern explained:**
>
> ```
> envFrom:                        # "Import all environment variables from..."
> - configMapRef:                 # ...this ConfigMap
>     name: documind-config       # Every key in documind-config becomes an env var
> - secretRef:                    # ...and this Secret
>     name: documind-secrets      # Every key in documind-secrets becomes an env var
> ```
>
> **vs the `env:` pattern from Phase 2:**
> ```yaml
> env:                            # "Set these specific environment variables"
> - name: REDIS_URL               # One at a time
>   valueFrom:
>     configMapKeyRef:
>       name: documind-config
>       key: REDIS_URL
> ```
>
> **When to use which:**
> - `envFrom` → When the pod needs **all** config from a ConfigMap (our case)
> - `env` with `valueFrom` → When the pod only needs **specific** keys, or you want to rename them

### 6.2 Apply and verify

```bash
# Apply the updated deployment
kubectl apply -f k8s/base/fastapi-deployment.yaml

# Watch the rolling update happen
kubectl get pods -l app=fastapi --watch
# You'll see new pods start with the new config, old pods terminate

# Once pods are 1/1 Running, verify the env vars are injected
kubectl exec deployment/fastapi -- env | sort | grep -E "REDIS|NEO4J|QDRANT|OLLAMA|LLM"
```

**Expected output:**
```
LLM_PROVIDER=ollama
NEO4J_PASSWORD=password
NEO4J_URI=bolt://neo4j-service:7687
NEO4J_USER=neo4j
OLLAMA_BASE_URL=http://ollama-service:11434
QDRANT_HOST=qdrant-service
QDRANT_PORT=6333
REDIS_URL=redis://redis-service:6379/0
```

> **🎓 The "aha" moment:** Notice `NEO4J_PASSWORD=password` is listed even though it comes from a Secret. From the pod's perspective, ConfigMap and Secret values are **just environment variables** — the pod doesn't know or care where they came from. The security boundary is at the K8s API level (who can read Secrets vs ConfigMaps).

---

## Step 7: Deploy Redis with Persistent Storage

Redis is the message broker for Celery and stores task state via `StateManager`. Let's deploy it properly.

### 7.1 Understand why Redis uses a Deployment (not StatefulSet)

| Factor | Redis in DocuMind | Decision |
|--------|-------------------|----------|
| Replicas needed | 1 (single instance) | No multi-node complexity |
| Data criticality | Task queue + status tracking | Important for UX, but rebuildable |
| Needs stable hostname | No — just `redis-service` | ClusterIP Service is sufficient |
| Needs stable storage | Yes — task state across restarts | PVC with Deployment |

> **📖 Redis vs Neo4j decision:**
> Redis here is a simple single-instance cache/broker. For this use case, a **Deployment + PVC** is simpler than a StatefulSet. You'd use a StatefulSet for Redis only if running Redis Cluster (multi-node replication) — that's overkill here.

### 7.2 Create the PersistentVolumeClaim

Create the file `k8s/base/redis-pvc.yaml`:

```yaml
# ─── PVC: Redis Data Storage ───────────────────────────────────
# Requests 1Gi of storage for Redis's append-only file (AOF).
#
# HOW THIS WORKS (Minikube):
# 1. You create this PVC ("I need 1Gi")
# 2. Minikube's 'standard' StorageClass sees the request
# 3. It automatically creates a PersistentVolume (1Gi folder on disk)
# 4. The PVC is "Bound" to that PV
# 5. Any pod that mounts this PVC gets access to that folder
#
# WHY 1Gi?
# Redis in DocuMind stores Celery task metadata and document statuses.
# That's tiny — maybe a few MB. 1Gi gives plenty of headroom.
# ────────────────────────────────────────────────────────────────

apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: redis-data
  labels:
    app: redis
spec:
  accessModes:
    - ReadWriteOnce          # Only one node can mount this at a time
                             # Fine for single-instance Redis
  resources:
    requests:
      storage: 1Gi           # How much disk space to reserve
  storageClassName: standard  # Minikube's default — auto-provisions the PV
```

> **📖 Access modes explained:**
> - `ReadWriteOnce (RWO)` — One node can mount read-write. Perfect for single-pod databases.
> - `ReadWriteMany (RWX)` — Multiple nodes can mount read-write. Needs special storage (NFS, EFS).
> - `ReadOnlyMany (ROX)` — Multiple nodes can mount read-only. Good for shared config files.
>
> For Redis, Neo4j, Qdrant — all single-instance — you'll always use `ReadWriteOnce`.

### 7.3 Create the Redis Deployment

Create the file `k8s/base/redis-deployment.yaml`:

```yaml
# ─── DEPLOYMENT: Redis (Message Broker + State Store) ──────────
#
# WHAT THIS REPLACES from docker-compose:
#   redis:
#     image: redis:alpine
#     container_name: documind-redis
#     networks: [documind-net]
#
# WHAT'S NEW IN K8S:
# - Persistent storage via PVC (data survives pod restarts)
# - Resource limits (Redis won't eat all your RAM)
# - Health checks via redis-cli ping
# ────────────────────────────────────────────────────────────────

apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  labels:
    app: redis
    component: database
spec:
  replicas: 1              # Single instance — Redis Cluster is overkill here
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
        component: database
    spec:
      containers:
      - name: redis
        image: redis:alpine
        imagePullPolicy: IfNotPresent

        ports:
        - name: redis
          containerPort: 6379
          protocol: TCP

        # ── PERSISTENT STORAGE ──
        # Mount the PVC at Redis's data directory
        volumeMounts:
        - name: redis-storage
          mountPath: /data        # Redis default data directory

        # ── RESOURCE LIMITS ──
        resources:
          requests:
            memory: "128Mi"       # Redis is lightweight for our use case
            cpu: "100m"
          limits:
            memory: "256Mi"       # Cap at 256Mi — enough for task state
            cpu: "250m"

        # ── HEALTH CHECKS ──
        # Redis has a built-in PING command — perfect for probes
        livenessProbe:
          exec:
            command: ["redis-cli", "ping"]
          initialDelaySeconds: 5
          periodSeconds: 10
          timeoutSeconds: 3
          failureThreshold: 3

        readinessProbe:
          exec:
            command: ["redis-cli", "ping"]
          initialDelaySeconds: 3
          periodSeconds: 5
          timeoutSeconds: 2
          failureThreshold: 2

      # ── VOLUME DEFINITION ──
      # Links the volumeMount above to the actual PVC
      volumes:
      - name: redis-storage
        persistentVolumeClaim:
          claimName: redis-data   # References the PVC you created
```

> **📖 Volume mounting chain explained:**
> ```
> Container                Volume Mount               Volume                PVC
> ─────────                ────────────               ──────                ───
> redis process            name: redis-storage        name: redis-storage   claimName: redis-data
> writes to /data    →     mountPath: /data      →    pvc: redis-data  →    1Gi, RWO, standard
> ```
> The names `redis-storage` on the `volumeMount` and `volume` must match — that's how K8s links them. The `claimName` must match your PVC name.

### 7.4 Create the Redis Service

Create the file `k8s/base/redis-service.yaml`:

```yaml
# ─── SERVICE: Redis ────────────────────────────────────────────
# ClusterIP Service — only reachable from inside the cluster.
# FastAPI and Celery connect to "redis-service:6379".
#
# WHY ClusterIP (not NodePort)?
# Redis should NEVER be exposed outside the cluster.
# Only your backend pods need to reach it.
# ────────────────────────────────────────────────────────────────

apiVersion: v1
kind: Service
metadata:
  name: redis-service         # This is the DNS name! "redis-service" resolves inside the cluster.
  labels:
    app: redis
spec:
  type: ClusterIP             # Internal only — no external access
  selector:
    app: redis                # Routes to pods with label app=redis
  ports:
  - name: redis
    port: 6379                # Service port (what other pods connect to)
    targetPort: 6379          # Pod port (where Redis actually listens)
    protocol: TCP
```

> **📖 Why `redis-service` and not just `redis`?**
> In your docker-compose, the hostname is `redis` (the service name). In K8s, the DNS name is the **Service name**, not the Deployment name. We chose `redis-service` because:
> 1. It clearly indicates this is a K8s Service
> 2. It matches the `REDIS_URL` in your ConfigMap: `redis://redis-service:6379/0`
> 3. Convention: `<app>-service` makes YAML files easier to scan

### 7.5 Deploy Redis

```bash
# Apply in order: PVC first (storage), then Deployment (pods), then Service (networking)
kubectl apply -f k8s/base/redis-pvc.yaml
kubectl apply -f k8s/base/redis-deployment.yaml
kubectl apply -f k8s/base/redis-service.yaml

# Watch Redis start
kubectl get pods -l app=redis --watch
# Expected: redis-xxx   1/1   Running   0   10s

# Verify the PVC is bound
kubectl get pvc
# Expected:
# NAME         STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS   AGE
# redis-data   Bound    pvc-abc123                                 1Gi        RWO            standard       30s

# Verify the Service
kubectl get service redis-service
# Expected:
# NAME            TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
# redis-service   ClusterIP   10.96.123.45    <none>        6379/TCP   10s

# Test Redis from inside the cluster
kubectl exec deployment/redis -- redis-cli ping
# Expected: PONG
```

> **🎓 Learning moment:** Run `kubectl get pv` to see the PersistentVolume that Minikube auto-created for your PVC. It's named something like `pvc-abc123...`. You didn't create it — the StorageClass's provisioner did it automatically. This is **dynamic provisioning**.

### 7.6 Test Redis persistence

This proves your data survives pod restarts:

```bash
# Write some test data
kubectl exec deployment/redis -- redis-cli SET test_key "phase3_works"
# Expected: OK

kubectl exec deployment/redis -- redis-cli GET test_key
# Expected: "phase3_works"

# Now kill the Redis pod (simulate a crash)
kubectl delete pod -l app=redis

# Wait for the new pod to start
kubectl get pods -l app=redis --watch
# Wait for 1/1 Running

# Check if data survived!
kubectl exec deployment/redis -- redis-cli GET test_key
# Expected: "phase3_works" 🎉
```

> **📖 Why did data survive?** The PVC (`redis-data`) exists independently of the pod. When K8s killed the old pod and created a new one, the new pod mounted the **same PVC** — same data directory, same files. This is exactly what PVCs are for.

---

## Step 8: Verify FastAPI ↔ Redis Connection

Now that Redis is running, your FastAPI pods should be able to connect to it.

### 8.1 Restart FastAPI pods to pick up the live Redis

```bash
# Restart to re-initialize connections
kubectl rollout restart deployment fastapi

# Watch pods come up
kubectl get pods -l app=fastapi --watch
# Wait for both pods to show 1/1 Running
```

### 8.2 Check the logs

```bash
kubectl logs -l app=fastapi --tail=10
```

**What to look for:**
```
✅ StateManager connected to Redis          ← Redis is now reachable!
⚠️ Qdrant not available yet (...)           ← Expected — Qdrant not deployed yet
❌ Neo4j Connection Failed: ...              ← Expected — Neo4j not deployed yet
```

If you see `✅ StateManager connected to Redis`, the ConfigMap + Service DNS + Redis deployment are all working together!

### 8.3 Test the full chain from outside

```bash
# Health check should still work
curl $(minikube service fastapi-service --url)/health

# Test the dashboard endpoint — Redis status should show "connected"
curl -s $(minikube service fastapi-service --url)/dashboard | python3 -m json.tool | grep redis
# Expected: "redis": "connected"
```

---

## Step 9: Deploy the Celery Worker

The Celery worker uses the **same Docker image** as FastAPI but with a different command. It connects to Redis as its broker.

### 9.1 Create the Worker Deployment

Create the file `k8s/base/worker-deployment.yaml`:

```yaml
# ─── DEPLOYMENT: Celery Worker ─────────────────────────────────
#
# WHAT THIS REPLACES from docker-compose:
#   worker:
#     build: ./backend
#     command: celery -A celery_app.celery_app worker --loglevel=info
#     env_file: .env
#     depends_on: [redis, init-ollama]
#
# KEY DIFFERENCES IN K8S:
# - Same image as FastAPI, different CMD (via 'command' override)
# - Uses same ConfigMap & Secret (shared config)
# - No depends_on — K8s handles startup order via readiness probes
# ────────────────────────────────────────────────────────────────

apiVersion: apps/v1
kind: Deployment
metadata:
  name: worker
  labels:
    app: worker
    component: backend
spec:
  replicas: 1               # Start with 1 worker — scale up if queue builds up
  selector:
    matchLabels:
      app: worker
  template:
    metadata:
      labels:
        app: worker
        component: backend
    spec:
      containers:
      - name: worker
        image: documind-fastapi:v1.1       # Same image as FastAPI!
        imagePullPolicy: IfNotPresent

        # ── OVERRIDE THE DEFAULT COMMAND ──
        # The Dockerfile CMD is "uvicorn main:app ..."
        # We override it to run Celery instead.
        command: ["celery"]
        args:
          - "-A"
          - "celery_app.celery_app"
          - "worker"
          - "--loglevel=info"
          - "--concurrency=2"              # Limit concurrent tasks (save RAM)

        # ── SHARED CONFIG ──
        # Same ConfigMap & Secret as FastAPI — one source of truth!
        envFrom:
        - configMapRef:
            name: documind-config
        - secretRef:
            name: documind-secrets

        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"

        # ── HEALTH CHECK ──
        # Celery workers don't serve HTTP. Use a command-based probe.
        livenessProbe:
          exec:
            command:
              - "celery"
              - "-A"
              - "celery_app.celery_app"
              - "inspect"
              - "ping"
              - "--timeout=5"
          initialDelaySeconds: 30
          periodSeconds: 30
          timeoutSeconds: 10
          failureThreshold: 3

      # ── SHARED UPLOADS VOLUME ──
      # The worker needs access to uploaded files for document processing.
      # For now, use an emptyDir. In Phase 4+, you'd use a shared PVC (RWX)
      # or object storage (MinIO/S3) for true multi-pod file sharing.
        volumeMounts:
        - name: uploads
          mountPath: /app/uploads

      volumes:
      - name: uploads
        emptyDir: {}          # Temporary — files won't survive pod restarts
                              # This is fine for now since uploads are also on the API pod
```

> **📖 Key decisions:**
>
> **Why `command` + `args`?** This overrides the Dockerfile's `CMD`. In K8s:
> - `command` = Docker `ENTRYPOINT`
> - `args` = Docker `CMD`
>
> **Why `concurrency=2`?** Each Celery worker process loads the full ML pipeline (~500MB RAM). With `--concurrency=2`, the worker runs 2 processes = ~1GB RAM cap. Matches our resource limits.
>
> **Why `emptyDir` for uploads?** This is a temporary solution. When FastAPI and the worker run in separate pods, they can't share files via filesystem. The proper fix (Phase 4+) is shared storage or object storage. For now, Celery tasks that need file access might fail — that's expected and we'll fix it later.

### 9.2 Deploy the worker

```bash
kubectl apply -f k8s/base/worker-deployment.yaml

# Watch it start
kubectl get pods -l app=worker --watch
# Expected: worker-xxx   1/1   Running   0   30s

# Check logs
kubectl logs -l app=worker --tail=20
```

**Expected logs:**
```
 -------------- celery@worker-xxx-yyy v5.x.x (opalescent)
--- ***** -----
--- * *** --- Connected to redis://redis-service:6379/0
-- * - **** --- 
- ** ---------- [queues]
- *** --- *--- .> celery   exchange=celery(direct) key=celery
```

The key line is `Connected to redis://redis-service:6379/0` — the worker found Redis through the K8s Service DNS name from the ConfigMap!

---

## Step 10: Test the Full Pipeline

### 10.1 Run the status script

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
fastapi   2/2     2            2           1h
redis     1/1     1            1           10m
worker    1/1     1            1           2m

── Pods ─────────────────────────────────
NAME                       READY   STATUS    RESTARTS   AGE
fastapi-xxx                1/1     Running   0          5m
fastapi-yyy                1/1     Running   0          5m
redis-zzz                  1/1     Running   0          10m
worker-aaa                 1/1     Running   0          2m

── Services ─────────────────────────────
NAME              TYPE        CLUSTER-IP      PORT(S)          AGE
fastapi-service   NodePort    10.96.x.x       8000:30800/TCP   1h
kubernetes        ClusterIP   10.96.0.1       443/TCP          2h
redis-service     ClusterIP   10.96.x.x       6379/TCP         10m
```

### 10.2 Verify cross-service communication

```bash
# From FastAPI pod, ping Redis
kubectl exec deployment/fastapi -- python -c "
import redis
r = redis.Redis.from_url('redis://redis-service:6379/0')
print('Redis PING:', r.ping())
print('Redis INFO server:', r.info('server')['redis_version'])
"
```

### 10.3 Test Redis persistence with Celery state

```bash
# From FastAPI pod, create a test state entry
kubectl exec deployment/fastapi -- python -c "
from state_manager import StateManager
sm = StateManager()
sm.set_processing('k8s-test.pdf', 'test-task-123')
print('Status:', sm.get_status('k8s-test.pdf'))
"

# Kill Redis pod
kubectl delete pod -l app=redis

# Wait for new Redis pod
kubectl get pods -l app=redis --watch

# Verify state survived!
kubectl exec deployment/fastapi -- python -c "
from state_manager import StateManager
sm = StateManager()
print('Status after restart:', sm.get_status('k8s-test.pdf'))
"
```

---

## Step 11: Update the ConfigMap (Live Config Changes)

One of the best things about ConfigMaps is that you can update configuration **without rebuilding Docker images**.

### 11.1 Try a live config change

```bash
# Change the LangChain project name
kubectl edit configmap documind-config
# Find LANGCHAIN_PROJECT and change it to "DocuMind_K8s_Phase3"
# Save and exit (:wq in vim)

# The ConfigMap is updated, but pods still have the old values!
# Pods read env vars at startup, so you need to restart:
kubectl rollout restart deployment fastapi
kubectl rollout restart deployment worker

# Verify
kubectl exec deployment/fastapi -- printenv LANGCHAIN_PROJECT
# Expected: DocuMind_K8s_Phase3
```

> **📖 Why do pods need a restart?**
> Environment variables are read at process startup. Unlike volume-mounted ConfigMaps (which K8s can hot-reload), env var-based configs require a pod restart. This is by design — it prevents unexpected behavior from config changes mid-request.
>
> In production, you'd version your ConfigMaps (`documind-config-v2`) and update the Deployment to reference the new version, triggering a controlled rolling update.

---

## Step 12: Debugging Common Issues

### Issue 1: Pod can't find ConfigMap/Secret

```bash
# Symptom: Pod stuck in CreateContainerConfigError
kubectl get pods
# fastapi-xxx   0/1   CreateContainerConfigError   0   10s

# Diagnosis
kubectl describe pod fastapi-xxx
# Events: Error: configmap "documind-config" not found

# Fix: Apply the ConfigMap first
kubectl apply -f k8s/base/documind-configmap.yaml
```

### Issue 2: PVC stuck in Pending

```bash
# Symptom
kubectl get pvc
# redis-data   Pending                              standard   30s

# Diagnosis
kubectl describe pvc redis-data
# Events: waiting for a volume to be created

# Fix (Minikube): Make sure the default StorageClass exists
kubectl get storageclass
# If empty, re-enable:
minikube addons enable default-storageclass
minikube addons enable storage-provisioner
```

### Issue 3: Worker can't connect to Redis

```bash
# Symptom: Worker logs show "Error connecting to redis-service:6379"

# Check 1: Is Redis running?
kubectl get pods -l app=redis
# Should show 1/1 Running

# Check 2: Does the Service exist?
kubectl get service redis-service
# Should show ClusterIP with port 6379

# Check 3: Can you reach Redis from the worker pod?
kubectl exec deployment/worker -- redis-cli -h redis-service ping
# Expected: PONG

# Check 4: Is the ConfigMap's REDIS_URL correct?
kubectl get configmap documind-config -o jsonpath='{.data.REDIS_URL}'
# Expected: redis://redis-service:6379/0
```

---

## ✅ Phase 3 Checklist

### Knowledge Check
- [ ] Can explain ConfigMap vs Secret and when to use each
- [ ] Understand `envFrom` vs `env[].valueFrom` patterns
- [ ] Know the PV → PVC → Pod volume mounting chain
- [ ] Understand why ClusterIP is used for internal services
- [ ] Know how K8s DNS resolves Service names to pod IPs

### Hands-On Check
```bash
# 1. ConfigMap and Secret exist
kubectl get configmap documind-config
kubectl get secret documind-secrets

# 2. FastAPI uses envFrom (no more hardcoded env vars)
kubectl exec deployment/fastapi -- printenv REDIS_URL
# Expected: redis://redis-service:6379/0

# 3. Redis running with persistent storage
kubectl get pvc redis-data
# Expected: STATUS=Bound
kubectl exec deployment/redis -- redis-cli ping
# Expected: PONG

# 4. Worker connected to Redis
kubectl logs -l app=worker --tail=5 | grep -i "connected"
# Expected: Connected to redis://redis-service:6379/0

# 5. Data survives pod restart
kubectl exec deployment/redis -- redis-cli SET phase3 "complete"
kubectl delete pod -l app=redis
sleep 15
kubectl exec deployment/redis -- redis-cli GET phase3
# Expected: "complete"
```

### Files Created
- [ ] `k8s/base/documind-configmap.yaml` — Shared environment configuration
- [ ] `k8s/base/documind-secret.yaml` — Passwords and API keys
- [ ] `k8s/base/redis-pvc.yaml` — Persistent storage for Redis
- [ ] `k8s/base/redis-deployment.yaml` — Redis Deployment with PVC mount
- [ ] `k8s/base/redis-service.yaml` — ClusterIP Service for Redis
- [ ] `k8s/base/worker-deployment.yaml` — Celery worker Deployment
- [ ] Updated `k8s/base/fastapi-deployment.yaml` — Refactored to use envFrom

---

## 🎓 New Concepts This Phase (Beyond Phase 2)

| Concept | What It Is | Why You Need It |
|---------|-----------|-----------------| 
| **ConfigMap** | External key-value store for config | Single source of truth, separate config from code |
| **Secret** | Like ConfigMap but for sensitive data | Don't put passwords in Deployment YAML |
| **PersistentVolumeClaim** | Storage request that outlives pods | Database data survives crashes and restarts |
| **Dynamic Provisioning** | StorageClass auto-creates PVs | You don't need to pre-create storage |
| **envFrom** | Inject all keys from ConfigMap/Secret | Cleaner than listing each env var manually |
| **ClusterIP Service** | Internal-only Service type | Databases should never be exposed externally |
| **Volume Mount Chain** | volumeMount → volume → PVC → PV | How storage flows from cluster to container |

---

**Next up: Phase 4 — StatefulSets for Qdrant and Neo4j. You'll learn why databases need StatefulSets (not Deployments) and deploy the vector DB and graph DB with persistent storage.** 🚀
