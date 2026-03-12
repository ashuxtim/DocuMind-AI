# Phase 2 — Deployments & Services: Migrate FastAPI to Kubernetes

In Phase 1 you learned pods are ephemeral — kill them and they're gone. Now you'll learn how **Deployments** keep your app alive and **Services** give it a stable address. By the end, your DocuMind FastAPI backend will be running on K8s with 2 replicas, health checks, and auto-healing.

---

## Step 1: Theory — Deployments: Why Bare Pods Are Dangerous

### 1.1 The Problem You Saw in Phase 1

Remember when you ran `kubectl delete pod nginx-test`? The pod disappeared forever. In production, pods crash for many reasons:
- Out of memory (OOM killed)
- Application bug / exception
- Node hardware failure
- Network partition

**Bare pods have no supervisor.** When they die, nobody recreates them.

### 1.2 Enter Deployments — The Supervisor Pattern

A Deployment wraps your pods in a management layer:

```
                  YOU define:
                  "I want 2 FastAPI pods running"
                          ↓
                  ┌─── Deployment ──────────────────┐
                  │   name: fastapi                  │
                  │   replicas: 2                    │  ← Your DESIRED state
                  │                                  │
                  │   ┌── ReplicaSet ──────────────┐ │
                  │   │  Ensures exactly 2 pods    │ │  ← The enforcer
                  │   │                            │ │
                  │   │  ┌─── Pod ──┐ ┌─── Pod ──┐ │ │
                  │   │  │ fastapi  │ │ fastapi  │ │ │  ← ACTUAL state
                  │   │  │ abc123   │ │ def456   │ │ │
                  │   │  └──────────┘ └──────────┘ │ │
                  │   └────────────────────────────┘ │
                  └──────────────────────────────────┘
```

> **📖 The chain of command:**
> - **Deployment** → declares desired state (replicas, image version, update strategy)
> - **ReplicaSet** → enforces the desired pod count (you rarely interact with this directly)
> - **Pods** → the actual running containers
>
> When you delete a pod, the ReplicaSet notices the actual count dropped below desired and **immediately creates a replacement**. This is **self-healing**.

### 1.3 What Makes Deployments Special?

| Feature | Bare Pod | Deployment |
|---------|----------|-----------|
| Auto-restart on crash | ❌ No | ✅ Yes (via ReplicaSet) |
| Scale replicas | ❌ No | ✅ `kubectl scale --replicas=5` |
| Rolling updates | ❌ No | ✅ Zero-downtime deploys |
| Rollback | ❌ No | ✅ `kubectl rollout undo` |
| Health monitoring | ❌ No | ✅ Liveness & readiness probes |

> **💡 Docker Compose comparison:**
> Your `docker-compose.yml` has `restart: always` (implicitly) — that's Docker's basic auto-restart. K8s Deployments go much further: they track **revision history**, support **rolling updates** (replace pods one-by-one without downtime), and can **rollback** to any previous version.

---

## Step 2: Theory — Services: Giving Pods a Stable Address

### 2.1 The Problem: Pods Get New IPs Every Time

Every time a pod is created, it gets a **random cluster IP**. When a Deployment recreates a pod (after crash or scaling), the new pod has a **different IP**. 

Your FastAPI backend needs to be reachable at a **consistent address** — that's what Services provide.

```
Without Service:
  Frontend → 10.244.0.5:8000  (FastAPI pod 1)
                                ← Pod dies, new pod gets 10.244.0.9
  Frontend → 10.244.0.5:8000  ← BROKEN! Old IP is gone

With Service:
  Frontend → fastapi-service:8000 → [load balances to]
                                     ├→ Pod 1 (10.244.0.5)
                                     └→ Pod 2 (10.244.0.7)
                                ← Pod 1 dies, replaced by Pod 3 (10.244.0.9)
  Frontend → fastapi-service:8000 → [automatically updates to]
                                     ├→ Pod 3 (10.244.0.9)
                                     └→ Pod 2 (10.244.0.7)
                                ← Frontend never knew anything changed!
```

### 2.2 How Services Find Pods: Label Selectors

Services don't know pod names or IPs. Instead, they use **label selectors** — they say "route traffic to any pod with label `app: fastapi`":

```yaml
# Service says: "Route to pods with app=fastapi"
selector:
  app: fastapi

# Deployment creates pods with that label
template:
  metadata:
    labels:
      app: fastapi   ← MATCH! Traffic flows here
```

> **📖 This is fundamentally different from Docker Compose:**
> In Compose, `depends_on: backend` creates a direct link by container name. In K8s, the connection is **indirect** — Services find pods by label, not by name. This means pods can come and go freely without breaking the connection.

### 2.3 Service Types — When to Use Which

| Type | Accessible From | Use Case | In DocuMind |
|------|----------------|----------|-------------|
| **ClusterIP** | Inside cluster only | Backend services talking to each other | Redis, Neo4j, Qdrant, Ollama |
| **NodePort** | Your machine (via `<node-ip>:<port>`) | Development & testing | FastAPI during development |
| **LoadBalancer** | Internet (via cloud LB) | Production external access | FastAPI in production |

> **💡 For DocuMind:**
> - FastAPI gets a **NodePort** so you can access it from your browser during development
> - Redis, Neo4j, Qdrant will get **ClusterIP** services (Phase 3-4) — only reachable by other pods inside the cluster
> - Eventually, an **Ingress** (Phase 5) will replace the NodePort with a proper domain

---

## Step 3: Theory — Health Probes: K8s Checks On Your App

K8s doesn't just start your container and forget about it. It **continuously monitors** health using two types of probes:

### 3.1 Liveness Probe — "Is the process alive?"

```
K8s asks every 10 seconds: "Hey pod, are you alive?"
Pod responds: HTTP 200 → Great, keep running
Pod responds: HTTP 500 (or no response) → KILL IT, create replacement
```

**Use case:** Detect deadlocks, infinite loops, zombie processes. If your FastAPI process hangs but doesn't crash, the liveness probe catches it.

### 3.2 Readiness Probe — "Can you handle traffic?"

```
K8s asks every 5 seconds: "Hey pod, ready for requests?"
Pod responds: HTTP 200 → Add to Service load balancer
Pod responds: HTTP 503 → Remove from Service (but don't kill!)
```

**Use case:** During startup, your FastAPI app needs time to load ML models and connect to databases. The readiness probe tells K8s "don't send traffic until I'm ready."

### 3.3 The Difference Matters

```
Scenario: FastAPI is starting up, loading sentence-transformers model...

                    Time 0s ──────── Time 15s ──────── Time 30s
Liveness:           Skip (initialDelaySeconds=30)      ✅ 200 OK
Readiness:          ❌ 503 (loading)   ❌ 503 (loading)  ✅ 200 OK

Traffic routing:    ❌ No traffic      ❌ No traffic     ✅ Traffic flows
Pod status:         Running           Running           Running + Ready

Without readiness probe:
Traffic routing:    ✅ Sends traffic!  → Users get errors! 💥
```

> **📖 DocuMind context:** Your backend imports heavy modules at startup (`sentence-transformers`, `qdrant_client`, `neo4j`). Without a readiness probe, K8s would send traffic before these are loaded, causing 500 errors for the first few seconds.

---

## Step 4: Add a Health Endpoint to DocuMind

Your `main.py` currently has no `/health` endpoint. K8s needs one for its probes. You'll add a **lightweight** endpoint that confirms the app is alive.

### 4.1 Add the `/health` endpoint

Open `backend/main.py` and add this endpoint **after the CORS middleware setup and before the global instances section** (around line 40):

```python
# --- HEALTH CHECK (for Kubernetes probes) ---
@app.get("/health")
async def health_check():
    """
    Lightweight health check for Kubernetes liveness & readiness probes.
    
    WHY THIS EXISTS:
    - Kubernetes calls this endpoint every few seconds
    - Liveness probe: If this fails, K8s kills and restarts the pod
    - Readiness probe: If this fails, K8s stops sending traffic to this pod
    
    WHY IT'S SIMPLE:
    - Health probes must be FAST (< 1 second response)
    - Don't check databases here — that's too slow and fragile
    - If Neo4j is down, your app is still "alive" (just degraded)
    """
    return {
        "status": "healthy",
        "service": "documind-backend",
        "version": "1.0.0"
    }
```

> **📖 Why not check databases in the health endpoint?**
> Imagine Neo4j goes down for 5 seconds. If your health check queries Neo4j, the probe fails, K8s kills your pod, starts a new one... which also can't reach Neo4j... and gets killed too. This creates a **crash cascade**.
>
> Best practice: Health probes check "is the process alive?" — not "are all dependencies working?" The `/dashboard` endpoint already does dependency health checks for your UI.

### 4.2 Where to add it in the file

Your `main.py` structure after the addition:

```python
# Line ~31: App creation
app = FastAPI(title="DocuMind AI")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Lines ~34-39: CORS middleware
app.add_middleware(CORSMiddleware, ...)

# ← ADD THE /health ENDPOINT HERE (new lines)

# Line ~41: Global instances
vector_db = VectorStore()
ingestor_read = DocuMindIngest()
...
```

> **⚠️ Important:** Add the `/health` endpoint **before** the global instance initialization (lines 42-49). This is because the global instances connect to Redis/Neo4j/Qdrant on import — if those are down during startup, the app might fail. But the `/health` endpoint doesn't need those connections, so placing it before them means it's available even during partial initialization.
> 
> Actually, since FastAPI registers routes regardless of order in the file, the position doesn't affect routing. But placing it before heavy initialization makes the code intent clearer — health check is a lightweight infrastructure concern, not business logic.

---

## Step 5: Build the Docker Image for K8s

Now you need to build a Docker image and load it into Minikube.

### 5.1 Understand the image loading flow

```
Your Machine:
  docker build → Creates image locally
       ↓
  minikube image load → Copies image INTO Minikube's Docker daemon
       ↓
Minikube (K8s cluster):
  Now K8s can use the image for pods
```

> **📖 Why this extra step?**
> Minikube runs in its own Docker environment (a Docker-in-Docker situation). Your local Docker and Minikube's Docker are **separate**. When the Deployment says `image: documind-fastapi:v1.0`, K8s looks in **Minikube's** Docker, not yours. So you must explicitly load the image.

### 5.2 Build and load

Run these commands from your DocuMind project root:

```bash
# Build the image — tag it with a version number (not :latest!)
docker build -t documind-fastapi:v1.0 ./backend

# This will take a few minutes the first time (installing Python deps)
# Expected: Successfully built abc123
# Expected: Successfully tagged documind-fastapi:v1.0

# Load into Minikube
minikube image load documind-fastapi:v1.0

# Verify it's available inside Minikube
minikube image ls | grep documind
# Expected: docker.io/library/documind-fastapi:v1.0
```

> **📖 Why `:v1.0` and not `:latest`?**
> - `:latest` is ambiguous — when you update your code, how does K8s know to pull the new image?
> - Versioned tags (`:v1.0`, `:v1.1`) make rollbacks trivial: "go back to v1.0"
> - In production, you'd use git SHAs: `:abc123f`

---

## Step 6: Write the Deployment Manifest

This is the real deal — your first Kubernetes Deployment for DocuMind.

### 6.1 Switch to the default namespace for DocuMind work

```bash
# Switch back to default namespace (we used 'learning' for practice)
kubectl config set-context --current --namespace=default
```

### 6.2 Create the Deployment YAML

Create the file `k8s/base/fastapi-deployment.yaml` with this content:

```yaml
# ─── DEPLOYMENT: DocuMind FastAPI Backend ───────────────────────
# A Deployment manages ReplicaSets which manage Pods.
# It ensures your desired number of pods are always running.
#
# WHAT THIS FILE TELLS K8S:
# "I want 2 pods running my FastAPI backend at all times.
#  Each pod needs 500m CPU and 512Mi RAM.
#  Kill and replace any pod that fails health checks."
# ────────────────────────────────────────────────────────────────

apiVersion: apps/v1       # Deployments live in the "apps" API group, version 1
kind: Deployment
metadata:
  name: fastapi           # How you refer to this deployment (kubectl get deployment fastapi)
  labels:
    app: fastapi          # Labels on the Deployment itself (for organizing)
    component: backend
spec:
  # ── REPLICA CONFIGURATION ──
  replicas: 2             # Run 2 identical pods (for redundancy + load balancing)
                          # If one dies, the other keeps serving while replacement starts

  # ── SELECTOR ──
  # "Which pods do I manage?" → Pods with label app=fastapi
  # This MUST match the labels in template.metadata.labels below
  selector:
    matchLabels:
      app: fastapi

  # ── POD TEMPLATE ──
  # This is the "recipe" for creating each pod.
  # Every pod created by this Deployment will look exactly like this.
  template:
    metadata:
      labels:
        app: fastapi        # MUST match selector above
        component: backend  # Extra labels for filtering (kubectl get pods -l component=backend)
    spec:
      containers:
      - name: fastapi
        image: documind-fastapi:v1.0
        imagePullPolicy: IfNotPresent   # Don't try to pull from Docker Hub — use local image
                                        # Without this, K8s tries to download from registry and fails

        ports:
        - name: http                    # Named port — makes configs more readable
          containerPort: 8000           # The port your FastAPI app listens on (from Dockerfile CMD)
          protocol: TCP

        # ── ENVIRONMENT VARIABLES ──
        # For now, we hardcode these. In Phase 3, we'll move them to ConfigMaps & Secrets.
        # These use K8s Service DNS names (e.g., "redis-service") which we'll create later.
        # Until those services exist, the app will start but won't connect to databases.
        env:
        - name: REDIS_URL
          value: "redis://redis-service:6379/0"
        - name: NEO4J_URI
          value: "bolt://neo4j-service:7687"
        - name: NEO4J_USER
          value: "neo4j"
        - name: NEO4J_PASSWORD
          value: "password"                     # ⚠️ Hardcoded for now — Secret in Phase 3
        - name: QDRANT_HOST
          value: "qdrant-service"
        - name: QDRANT_PORT
          value: "6333"
        - name: OLLAMA_BASE_URL
          value: "http://ollama-service:11434"
        - name: LLM_PROVIDER
          value: "ollama"
        - name: UPLOAD_FOLDER
          value: "./uploads"

        # ── RESOURCE MANAGEMENT ──
        # requests = guaranteed minimum (scheduler uses this to place pods)
        # limits   = hard cap (pod gets killed/throttled if exceeded)
        resources:
          requests:
            memory: "512Mi"     # Your FastAPI app needs ~400-500Mi at baseline
            cpu: "500m"         # 0.5 CPU cores
          limits:
            memory: "1Gi"       # Allow spikes up to 1Gi (e.g., during document processing)
            cpu: "1000m"        # Allow up to 1 full CPU core

        # ── LIVENESS PROBE ──
        # "Is the process alive?"
        # If this fails 3 times in a row, K8s kills the pod and creates a new one.
        livenessProbe:
          httpGet:
            path: /health       # The endpoint you just added!
            port: 8000
          initialDelaySeconds: 30   # Wait 30s before first check (app needs time to start)
          periodSeconds: 10         # Check every 10 seconds
          timeoutSeconds: 5         # Probe must respond within 5s
          failureThreshold: 3       # Kill after 3 consecutive failures

        # ── READINESS PROBE ──
        # "Can you handle traffic?"
        # If this fails, pod stays alive but gets removed from Service load balancer.
        readinessProbe:
          httpGet:
            path: /health       # Same endpoint, but different purpose
            port: 8000
          initialDelaySeconds: 10   # Start checking earlier than liveness
          periodSeconds: 5          # Check more frequently
          timeoutSeconds: 3         # Tighter timeout
          failureThreshold: 2       # Remove from LB after 2 failures (more aggressive)
```

> **📖 Key decisions explained:**
> 
> **Why 2 replicas?** Redundancy. If one pod crashes or gets updated, the other keeps serving. For a learning project, 2 is enough; production might use 3-5.
>
> **Why `imagePullPolicy: IfNotPresent`?** Because your image is loaded locally into Minikube, not in Docker Hub. Without this, K8s tries to pull `documind-fastapi:v1.0` from the internet and gets `ImagePullBackOff`.
>
> **Why liveness `initialDelaySeconds: 30`?** Your app imports heavy Python modules (`sentence-transformers`, `qdrant_client`). If K8s starts checking health before imports finish, it would kill the pod before it even starts. 30 seconds gives it time.
>
> **Why readiness `initialDelaySeconds: 10`?** We want to know quickly when the pod is ready for traffic, so we start checking earlier. But the first few checks will fail (app still loading) — that's fine, they just mean "don't send traffic yet."

---

## Step 7: Write the Service Manifest

### 7.1 Create the Service YAML

Create the file `k8s/base/fastapi-service.yaml` with this content:

```yaml
# ─── SERVICE: DocuMind FastAPI ──────────────────────────────────
# A Service provides a stable network endpoint for your pods.
# Without this, you'd have to know each pod's random IP address.
#
# WHAT THIS FILE TELLS K8S:
# "Create a stable endpoint called 'fastapi-service'.
#  Route any traffic on port 8000 to pods with label app=fastapi.
#  Also expose it on node port 30800 so I can access it from my browser."
# ────────────────────────────────────────────────────────────────

apiVersion: v1             # Services are core resources (v1, no group prefix)
kind: Service
metadata:
  name: fastapi-service    # This becomes a DNS name inside the cluster!
                           # Other pods can reach your FastAPI at: http://fastapi-service:8000
  labels:
    app: fastapi
spec:
  type: NodePort           # Exposes the service on each node's IP at a static port
                           # For development: access via http://<minikube-ip>:30800
                           # In production: you'd use LoadBalancer or Ingress instead

  # ── SELECTOR ──
  # "Which pods should receive this traffic?"
  # MUST match the labels on your Deployment's pod template
  selector:
    app: fastapi           # Routes to ANY pod with label app=fastapi

  ports:
  - name: http
    port: 8000             # The port the Service listens on (inside cluster)
    targetPort: 8000       # The port on the pod to forward to (containerPort)
    nodePort: 30800        # The port on your machine (http://192.168.49.2:30800)
                           # Range: 30000-32767 (K8s restriction)
    protocol: TCP

  sessionAffinity: None    # Load balance evenly across pods (round-robin)
                           # Use "ClientIP" if you need sticky sessions
```

> **📖 Port terminology can be confusing. Here's the full picture:**
>
> ```
> Your Browser                    K8s Node (Minikube)              Pod
> ─────────────                   ───────────────────              ────
> http://192.168.49.2:30800  →    nodePort: 30800  →  port: 8000  →  targetPort: 8000
>                                                                     (containerPort)
>                                                                     
> Other Pod inside cluster:
> http://fastapi-service:8000  →  port: 8000  →  targetPort: 8000
> ```
>
> - **nodePort (30800)** = accessible from outside the cluster (your browser)
> - **port (8000)** = the Service's own port (used by other pods inside cluster)
> - **targetPort (8000)** = the actual port inside the container where FastAPI listens

---

## Step 8: Deploy to Kubernetes

Time to see it all come together.

### 8.1 Apply the manifests

```bash
# Apply the deployment first
kubectl apply -f k8s/base/fastapi-deployment.yaml

# Watch pods being created (Ctrl+C when both show "Running")
kubectl get pods -l app=fastapi --watch
```

**Expected output progression:**
```
NAME                       READY   STATUS              RESTARTS   AGE
fastapi-7d9c8b5f4d-abc12   0/1     ContainerCreating   0          2s
fastapi-7d9c8b5f4d-def34   0/1     ContainerCreating   0          2s
fastapi-7d9c8b5f4d-abc12   0/1     Running             0          5s
fastapi-7d9c8b5f4d-def34   0/1     Running             0          6s
fastapi-7d9c8b5f4d-abc12   1/1     Running             0          35s   ← READY!
fastapi-7d9c8b5f4d-def34   1/1     Running             0          36s   ← READY!
```

> **📖 Notice the `READY` column:**
> - `0/1` = Pod is running but readiness probe hasn't passed yet
> - `1/1` = Readiness probe passed — pod is receiving traffic
>
> The ~30 second delay is your `initialDelaySeconds` at work.

Now apply the service:

```bash
# Apply the service
kubectl apply -f k8s/base/fastapi-service.yaml

# Check the service
kubectl get service fastapi-service
```

**Expected output:**
```
NAME              TYPE       CLUSTER-IP     EXTERNAL-IP   PORT(S)          AGE
fastapi-service   NodePort   10.96.45.123   <none>        8000:30800/TCP   5s
```

### 8.2 Inspect what K8s created

```bash
# See the full deployment details
kubectl describe deployment fastapi

# Key sections to read:
# - Replicas: 2 desired | 2 updated | 2 total | 2 available
# - Events: deployment created, scaled to 2

# See the ReplicaSet (the middle layer you rarely touch directly)
kubectl get replicasets
# Notice: K8s automatically created a ReplicaSet for you

# Check pod logs (from both pods)
kubectl logs -l app=fastapi --tail=20
```

> **📖 What to look for in logs:**
> You might see connection errors to Redis/Neo4j/Qdrant — that's **expected** since those services don't exist in K8s yet. The important thing is that FastAPI starts and the `/health` endpoint works.

### 8.3 Check the service endpoints

```bash
# This is KEY — see which pods the service routes to
kubectl get endpoints fastapi-service
```

**Expected output:**
```
NAME              ENDPOINTS                           AGE
fastapi-service   10.244.0.5:8000,10.244.0.6:8000     30s
```

> **📖 What are endpoints?**
> Endpoints are the actual pod IPs that the Service routes traffic to. When a pod dies and a new one takes its place, the endpoint list automatically updates. This is how Services maintain stable connectivity.

---

## Step 9: Test Your Deployment

### 9.1 Access via Minikube

```bash
# Get the full URL for your service
minikube service fastapi-service --url
# Expected: http://192.168.49.2:30800

# Test the health endpoint
curl $(minikube service fastapi-service --url)/health
# Expected: {"status":"healthy","service":"documind-backend","version":"1.0.0"}
```

Alternative method — port-forward:

```bash
# Port-forward (useful if NodePort isn't working)
kubectl port-forward svc/fastapi-service 8000:8000

# In another terminal:
curl http://localhost:8000/health
```

### 9.2 Test Self-Healing (The "Aha!" Moment)

This is the moment Deployments click. Watch what happens when you kill a pod:

**Terminal 1 — Watch pods:**
```bash
kubectl get pods -l app=fastapi --watch
```

**Terminal 2 — Kill a pod:**
```bash
# Get pod names
kubectl get pods -l app=fastapi

# Delete one (replace with your actual pod name)
kubectl delete pod fastapi-7d9c8b5f4d-abc12
```

**What you'll see in Terminal 1:**
```
NAME                       READY   STATUS        RESTARTS   AGE
fastapi-7d9c8b5f4d-abc12   1/1     Terminating   0          5m    ← Dying
fastapi-7d9c8b5f4d-def34   1/1     Running       0          5m    ← Still serving!
fastapi-7d9c8b5f4d-ghi78   0/1     Pending       0          1s    ← Replacement spawned!
fastapi-7d9c8b5f4d-ghi78   0/1     ContainerCreating  0     2s
fastapi-7d9c8b5f4d-ghi78   1/1     Running       0          30s   ← Back to 2/2 pods!
```

> **🎓 The learning moment:**
> You didn't do anything. K8s detected the pod count dropped from 2 to 1, and the ReplicaSet controller **immediately** created a replacement. The Service never went offline because Pod 2 kept serving traffic the entire time. **This is self-healing.**

### 9.3 Test Scaling

```bash
# Scale to 3 replicas
kubectl scale deployment fastapi --replicas=3

# Watch
kubectl get pods -l app=fastapi
# Expected: 3 pods running

# Check endpoints — now 3 IPs
kubectl get endpoints fastapi-service

# Scale back to 2
kubectl scale deployment fastapi --replicas=2

# Watch a pod terminate gracefully
kubectl get pods -l app=fastapi --watch
```

> **📖 In production, you'd use `HorizontalPodAutoscaler` (HPA) instead of manual scaling:**
> ```bash
> kubectl autoscale deployment fastapi --cpu-percent=70 --min=2 --max=10
> ```
> This automatically scales based on CPU usage. But that's for later — manual scaling is perfect for learning.

### 9.4 Test Rolling Update (Bonus — Preview)

This previews what happens when you deploy a new version of your code:

```bash
# Check rollout history
kubectl rollout history deployment fastapi

# Simulate a config change (this triggers a new rollout)
kubectl set env deployment/fastapi DEMO_VERSION=v1.1

# Watch the rolling update
kubectl get pods -l app=fastapi --watch

# You'll see: new pods start → old pods terminate → zero downtime
```

> **📖 Rolling update strategy:**
> K8s replaces pods one at a time by default. It starts a new pod with the new config, waits for it to pass readiness, then kills an old pod. This ensures there's always at least 1 pod serving traffic — **zero downtime deployment**.

---

## Step 10: Debugging Common Issues

Here are issues you might encounter and how to solve them:

### Issue 1: Pods in `ImagePullBackOff`

```bash
# Symptom
kubectl get pods
# NAME                       READY   STATUS             RESTARTS   AGE
# fastapi-xxx                0/1     ImagePullBackOff   0          30s

# Diagnosis
kubectl describe pod fastapi-xxx
# Events: Failed to pull image "documind-fastapi:v1.0": not found

# Fix: Load image into Minikube
minikube image load documind-fastapi:v1.0

# Verify image exists in Minikube
minikube image ls | grep documind

# Also make sure your YAML has:
#   imagePullPolicy: IfNotPresent
```

### Issue 2: Pods in `CrashLoopBackOff`

```bash
# Symptom: Pod starts, crashes, restarts, crashes again
kubectl get pods
# NAME                       READY   STATUS             RESTARTS   AGE
# fastapi-xxx                0/1     CrashLoopBackOff   3          2m

# Diagnosis: Check logs
kubectl logs fastapi-xxx
kubectl logs fastapi-xxx --previous    # Logs from the LAST crash

# Common causes:
# - Missing Python module (requirements.txt issue)
# - Database connection timeout at startup (expected if Redis/Neo4j not deployed yet)
# - Port conflict
# - Environment variable missing

# Debug: Get a shell into the pod
kubectl exec -it fastapi-xxx -- /bin/bash
# If pod keeps crashing, override the command temporarily:
kubectl run debug-fastapi --image=documind-fastapi:v1.0 --command -- sleep infinity
kubectl exec -it debug-fastapi -- /bin/bash
# Now explore the container manually
```

### Issue 3: Service returns no endpoints

```bash
# Symptom
kubectl get endpoints fastapi-service
# NAME              ENDPOINTS   AGE
# fastapi-service   <none>      30s    ← Empty!

# Cause: Label mismatch between Service selector and Pod labels
# Check Service selector:
kubectl describe service fastapi-service | grep Selector
# Selector: app=fastapi

# Check Pod labels:
kubectl get pods --show-labels
# Make sure pods have "app=fastapi" in their labels
```

---

## Step 11: Create a Status Helper Script

Create the file `k8s/scripts/k8s-status.sh` with this content:

```bash
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
```

Make it executable and run:

```bash
chmod +x k8s/scripts/k8s-status.sh
./k8s/scripts/k8s-status.sh
```

---

## ✅ Phase 2 Checklist

### Knowledge Check
- [ ] Can explain the Deployment → ReplicaSet → Pod chain of command
- [ ] Understand why `imagePullPolicy: IfNotPresent` is needed for local images
- [ ] Know the difference between liveness and readiness probes
- [ ] Understand how Services find pods via label selectors
- [ ] Know the 3 Service types and when to use each

### Hands-On Check
```bash
# 1. Deployment running with 2 pods
kubectl get deployment fastapi
# Expected: READY 2/2

# 2. Both pods healthy
kubectl get pods -l app=fastapi
# Expected: 2 pods, STATUS=Running, READY=1/1

# 3. Service has endpoints
kubectl get endpoints fastapi-service
# Expected: 2 pod IPs listed

# 4. Health endpoint accessible
curl $(minikube service fastapi-service --url)/health
# Expected: {"status":"healthy","service":"documind-backend","version":"1.0.0"}

# 5. Self-healing works
kubectl delete pod <any-fastapi-pod>
kubectl get pods -l app=fastapi --watch
# Expected: Replacement pod created immediately
```

### Files Created/Modified
- [ ] `backend/main.py` — Added `/health` endpoint
- [ ] `k8s/base/fastapi-deployment.yaml` — Deployment manifest
- [ ] `k8s/base/fastapi-service.yaml` — NodePort Service manifest
- [ ] `k8s/scripts/k8s-status.sh` — Status check script

---

## 🎓 New Concepts This Phase (Beyond Docker Compose)

| Concept | What It Is | Why You Need It |
|---------|-----------|-----------------|
| **Deployment** | Manages pod lifecycle, updates, scaling | Self-healing + zero-downtime updates |
| **ReplicaSet** | Ensures N pods are always running | The "enforcer" behind Deployments |
| **Service** | Stable network endpoint for ephemeral pods | Pods come and go; Services stay |
| **Label Selector** | How Services discover Pods | Decoupled — pods can be replaced freely |
| **Liveness Probe** | "Is the process alive?" | Detect and auto-fix zombied processes |
| **Readiness Probe** | "Can you handle traffic?" | Prevent routing to unready pods |
| **NodePort** | External access to cluster services | Development access from your browser |
| **Rolling Update** | Replace pods one-by-one during deploys | Zero-downtime deployments |

---

**Next up: Phase 3 — ConfigMaps, Secrets, and Volumes. You'll deploy Redis with persistent storage and connect Celery workers.** 🚀
