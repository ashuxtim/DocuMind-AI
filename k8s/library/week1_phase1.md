# Phase 1 — Foundation & Setup: Interactive Learning Guide

Welcome to Kubernetes! This guide walks you through everything step by step. **You'll type every command and create every file yourself** — that's how the concepts stick.

---

## Step 1: The Theory — Why Kubernetes? (30 min read)

Before touching any tools, let's understand *what problem we're solving*.

### Your Current World: Docker Compose

You already know Docker Compose well. Your `docker-compose.yml` runs 8 containers on **one machine**:

```
                    ┌─── Your Single Machine ───────────────┐
                    │                                        │
                    │   ollama ──→ init-ollama               │
                    │                                        │
                    │   redis   neo4j   qdrant               │
                    │     ↑       ↑       ↑                  │
                    │   backend (FastAPI) ──→ frontend        │
                    │   worker (Celery)                       │
                    │                                        │
                    │         documind-net (bridge)           │
                    └────────────────────────────────────────┘
```

**What Docker Compose can't do:**
- ❌ Run across multiple machines (no horizontal scaling)
- ❌ Auto-restart crashed containers reliably
- ❌ Rolling updates (deploy new version without downtime)
- ❌ Auto-scale based on load
- ❌ Manage storage lifecycle properly
- ❌ Built-in service discovery across nodes

### The Kubernetes World

Kubernetes solves all of the above. Think of it as **Docker Compose on steroids, for multiple machines**:

```
         ┌──── Control Plane (The Brain) ─────┐
         │                                      │
         │  API Server ← You talk to this       │
         │  etcd       ← Stores all state       │
         │  Scheduler  ← Decides WHERE to run   │
         │  Controller ← Ensures desired state  │
         └──────────────────────────────────────┘
                          ↓ manages ↓
         ┌──── Worker Node 1 ────┐  ┌──── Worker Node 2 ────┐
         │  kubelet (agent)      │  │  kubelet (agent)      │
         │  kube-proxy (network) │  │  kube-proxy (network) │
         │                       │  │                       │
         │  [Pod: backend]       │  │  [Pod: backend]       │
         │  [Pod: redis]         │  │  [Pod: qdrant]        │
         │  [Pod: neo4j]         │  │  [Pod: worker]        │
         └───────────────────────┘  └───────────────────────┘
```

### Key Concept Map: Docker Compose → Kubernetes

| Docker Compose | Kubernetes | What Changed? |
|---------------|------------|---------------|
| `services:` block | **Deployment** or **StatefulSet** | Deployments add auto-healing, rolling updates |
| Container | **Pod** | Pod wraps 1+ containers, adds shared networking |
| `ports:` mapping | **Service** | Stable endpoint that survives pod restarts |
| `environment:` | **ConfigMap** / **Secret** | Externalized, can be shared across deployments |
| `volumes:` | **PersistentVolumeClaim** | Storage managed by the cluster, not the host |
| `depends_on:` | **Init Containers** / **Readiness Probes** | K8s has better dependency management |
| `docker-compose.yml` | **YAML manifests** (one per resource) | Each K8s object gets its own file |
| `docker-compose up` | `kubectl apply -f .` | Declarative — K8s figures out what to do |

> **💡 Key mental model:** In Docker Compose, you *command* things to happen (`up`, `down`). In K8s, you *declare* what you want, and K8s figures out how to make it happen and **keeps it that way**.

---

## Step 2: Install Minikube (Your Local K8s Cluster)

Minikube creates a **single-node Kubernetes cluster inside a Docker container** on your machine. It's perfect for learning — you get a real K8s cluster without needing cloud infrastructure.

### 2.1 Install Minikube

Run these commands **one at a time** in your terminal:

```bash
# Download the Minikube binary
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64

# Install it to your system PATH
sudo install minikube-linux-amd64 /usr/local/bin/minikube

# Clean up the downloaded file
rm minikube-linux-amd64

# Verify it installed
minikube version
```

**Expected output:**
```
minikube version: v1.35.0
```

### 2.2 Install kubectl (The K8s CLI)

`kubectl` is how you **talk to** Kubernetes. Every command you'll ever run goes through this tool. Think of it as the `docker` CLI, but for K8s.

```bash
# Download kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"

# Install it
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# Clean up
rm kubectl

# Verify
kubectl version --client
```

**Expected output:**
```
Client Version: v1.32.x
```

### 2.3 Start Your Cluster

This is the big moment — you're creating a Kubernetes cluster!

```bash
# Start Minikube with enough resources for DocuMind
# --cpus=4     → Allocate 4 CPU cores
# --memory=8192 → Allocate 8GB RAM
# --driver=docker → Use Docker as the VM driver (you already have Docker)
minikube start --cpus=4 --memory=8192 --driver=docker
```

> **📖 What's happening behind the scenes?**
> Minikube is creating a Docker container that runs a full Linux VM with all K8s components:
> - **etcd** (the database that stores all cluster state)
> - **API server** (the REST API you'll talk to via kubectl)
> - **Scheduler** (decides which node runs which pod)
> - **Controller manager** (ensures desired state matches actual state)
> - **kubelet** (the agent that manages containers)
> - **kube-proxy** (handles networking)
>
> All of this runs **inside a single Docker container** for local development.

### 2.4 Verify Your Cluster

```bash
# Check cluster info — the API server URL
kubectl cluster-info

# Check your node (should show 1 node: "minikube")
kubectl get nodes

# Detailed node info (see CPU, memory, OS, container runtime)
kubectl describe node minikube
```

**Expected output for `kubectl get nodes`:**
```
NAME       STATUS   ROLES           AGE   VERSION
minikube   Ready    control-plane   1m    v1.32.0
```

> **💡 Notice:** The single node has the role `control-plane` — in Minikube, one node acts as **both** the brain (control plane) and the body (worker). In production, these are separate machines.

---

## Step 3: kubectl Practice — Your First Pods

Now the fun begins. Let's deploy, inspect, and destroy things.

### 3.1 Create a Namespace

Namespaces are like **folders** for your K8s resources. They keep things organized and isolated. Your DocuMind services will eventually live in their own namespace.

```bash
# Create a namespace for practicing
kubectl create namespace learning

# Switch to it (so all commands default to this namespace)
kubectl config set-context --current --namespace=learning

# Verify your current context
kubectl config get-contexts
```

> **📖 Why namespaces?**
> Without namespaces, everything goes in `default`. Imagine 5 teams deploying to the same cluster — namespaces prevent naming conflicts and allow resource quotas per team.

### 3.2 Deploy Your First Pod (Imperative Way)

```bash
# Create a pod running nginx (a simple web server)
# This is the "imperative" way — you're giving a direct command
kubectl run nginx-test --image=nginx:latest --port=80
```

Now inspect it:

```bash
# List pods — watch the STATUS column
kubectl get pods

# More details (which node it's on, its IP)
kubectl get pods -o wide

# Full details (events, status transitions, resource usage)
kubectl describe pod nginx-test
```

> **📖 What to look for in `describe`:**
> Scroll to the **Events** section at the bottom. You'll see:
> ```
> Type    Reason     Message
> ----    ------     -------
> Normal  Scheduled  Successfully assigned learning/nginx-test to minikube
> Normal  Pulling    Pulling image "nginx:latest"
> Normal  Pulled     Successfully pulled image
> Normal  Created    Created container nginx-test
> Normal  Started    Started container nginx-test
> ```
> This is the **lifecycle** of a pod: Scheduled → Image pulled → Container created → Started.

### 3.3 Interact with the Pod

```bash
# Check nginx logs
kubectl logs nginx-test

# Open a shell INSIDE the pod (like docker exec -it)
kubectl exec -it nginx-test -- /bin/bash

# Inside the pod, run:
ls -la
cat /etc/nginx/nginx.conf
curl localhost:80
exit
```

> **📖 The `--` separator:**
> In `kubectl exec -it nginx-test -- /bin/bash`, the `--` separates kubectl args from the command to run inside the container. Everything after `--` is passed to the container.

### 3.4 Access the Pod from Your Machine

Pods have internal cluster IPs that your machine can't reach directly. **Port-forwarding** creates a tunnel:

```bash
# Forward your machine's port 8080 to the pod's port 80
kubectl port-forward nginx-test 8080:80
```

Now open a **new terminal** and run:
```bash
curl http://localhost:8080
```

You should see the nginx welcome page HTML. Press `Ctrl+C` in the first terminal to stop port-forwarding.

> **📖 Port-forward vs Service:**
> Port-forwarding is a **debugging tool** — it connects *your laptop* directly to *one pod*. In production, you'll use **Services** (Day 2) which provide load balancing across multiple pods and stable DNS names.

### 3.5 Delete and Observe

```bash
# Delete the pod
kubectl delete pod nginx-test

# Verify it's gone
kubectl get pods
```

> **💡 Key learning:** The pod is gone forever. Nobody is watching to recreate it. This is why **bare pods are bad for production** — if it crashes, it's dead. That's what Deployments fix (Day 2).

---

## Step 4: Deploy a Pod the Declarative Way (YAML)

The imperative `kubectl run` is fine for quick tests. But in K8s, the **declarative** approach is king — you write YAML files that describe what you want, and K8s makes it happen.

### 4.1 Create your K8s directory structure

```bash
# Create the directory that will hold all K8s manifests
mkdir -p ~/Projects/DocuMind/k8s/base

# Also create a practice directory
mkdir -p ~/Projects/DocuMind/k8s/practice
```

### 4.2 Create your first YAML manifest

Create the file `k8s/practice/test-pod.yaml` in your project with this content:

```yaml
# Every K8s resource has these 4 top-level fields
apiVersion: v1              # Which K8s API version (v1 for core resources)
kind: Pod                   # What type of resource
metadata:                   # Identity — name, labels, namespace
  name: lifecycle-demo
  labels:                   # Labels are KEY-VALUE tags for organizing & selecting
    app: demo               # Services use these to find pods
    purpose: learning
spec:                       # Specification — what you WANT
  containers:
  - name: nginx
    image: nginx:1.25       # Pinned version (not :latest — be specific!)
    ports:
    - containerPort: 80
    resources:               # Resource management — crucial for production
      requests:              # "I need AT LEAST this much" (scheduler uses this)
        memory: "64Mi"
        cpu: "250m"          # 250 millicores = 0.25 CPU cores
      limits:                # "NEVER exceed this" (K8s kills container if exceeded)
        memory: "128Mi"
        cpu: "500m"          # 500 millicores = 0.5 CPU cores
```

> **📖 Understanding resource units:**
> - **Memory:** `Mi` = Mebibytes (1Mi ≈ 1MB). `64Mi` = 64 MB of RAM.
> - **CPU:** `m` = millicores. `1000m` = 1 full CPU core. `250m` = 25% of one core.
> - **requests** = guaranteed minimum (scheduler ensures this is available)
> - **limits** = hard cap (container gets killed/throttled if it exceeds this)
>
> **DocuMind context:** Your FastAPI backend will need ~512Mi memory and 500m CPU. Neo4j needs ~1Gi and 500m. These numbers matter when your cluster has limited resources.

### 4.3 Apply the YAML

```bash
# Apply — K8s reads the YAML and creates the resource
kubectl apply -f k8s/practice/test-pod.yaml

# Watch the pod lifecycle in real-time (Ctrl+C to stop)
kubectl get pods --watch

# When status shows "Running", describe it
kubectl describe pod lifecycle-demo
```

> **📖 `apply` vs `create`:**
> - `kubectl create` = "Create this. Error if it already exists."
> - `kubectl apply` = "Make reality match this YAML. Create if missing, update if different."
>
> **Always use `apply`** — it's idempotent (you can run it multiple times safely).

### 4.4 Clean up

```bash
# Delete using the same YAML file
kubectl delete -f k8s/practice/test-pod.yaml

# Verify
kubectl get pods
```

---

## Step 5: Analyze Your DocuMind Docker Compose for K8s Migration

This is the most important part of Day 1 — mapping your existing services to K8s objects.

### 5.1 Your Docker Compose Breakdown

Here's your actual `docker-compose.yml` mapped to K8s concepts:

```
┌──────────────────────────────────────────────────────────────┐
│                  YOUR DOCKER COMPOSE                         │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ← INIT CONTAINERS (K8s)        │
│  │  ollama   │  │init-ollama│    These will be handled       │
│  │  (LLM)   │  │  (setup)  │    differently in K8s          │
│  └──────────┘  └──────────┘                                  │
│                                                              │
│  ┌────────┐ ┌────────┐ ┌────────┐  ← STATEFULSETS (K8s)     │
│  │ redis  │ │ neo4j  │ │ qdrant │    Need persistent storage │
│  │(alpine)│ │(:latest)│ │(:latest)│   Stable identities      │
│  └────────┘ └────────┘ └────────┘                            │
│                                                              │
│  ┌──────────┐ ┌──────────┐   ← DEPLOYMENTS (K8s)            │
│  │ backend  │ │  worker  │     Stateless, scalable           │
│  │(FastAPI) │ │ (Celery) │     Can have multiple replicas    │
│  └──────────┘ └──────────┘                                   │
│                                                              │
│  ┌──────────┐                ← DEPLOYMENT + INGRESS (K8s)    │
│  │ frontend │                  Served via Ingress             │
│  │  (Nginx) │                                                │
│  └──────────┘                                                │
│                                                              │
│  documind-net (bridge)       ← K8s NETWORKING (automatic)    │
│                                 Services + DNS built-in      │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 Service Classification

| Service | Docker Image | Data? | K8s Object | Why? |
|---------|-------------|-------|-----------|------|
| `backend` | Custom (Python 3.12) | No state | **Deployment** | Stateless API — can have N replicas |
| `worker` | Same custom image | No state | **Deployment** | Stateless worker — scale based on queue |
| `frontend` | Custom (Nginx) | No state | **Deployment** | Static files — easily replicated |
| `redis` | `redis:alpine` | Queue data | **Deployment + PVC** | Simple persistence, single instance |
| `neo4j` | `neo4j:latest` | Graph data | **StatefulSet** | Needs stable identity + persistent data |
| `qdrant` | `qdrant/qdrant` | Vector data | **StatefulSet** | Needs stable identity + persistent data |
| `ollama` | `ollama/ollama` | Model files | **StatefulSet** | Large model storage needed |
| `init-ollama` | `curlimages/curl` | None | **Init Container** | One-time setup, not a standalone service |

### 5.3 Environment Variable Migration

Your `.env` file has these categories that map to K8s concepts:

| Category | Variables | K8s Object |
|----------|----------|-----------|
| **Non-sensitive config** | `REDIS_URL`, `NEO4J_URI`, `QDRANT_HOST`, `QDRANT_PORT`, `UPLOAD_FOLDER` | **ConfigMap** |
| **Secrets** | `NEO4J_PASSWORD`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `LANGCHAIN_API_KEY`, `LLAMA_CLOUD_API_KEY` | **Secret** |
| **Service discovery** | `OLLAMA_BASE_URL`, hostnames like `redis`, `neo4j` | **K8s Service DNS** (automatic!) |

> **💡 Key insight:** In Docker Compose, you use service names like `redis`, `neo4j` to connect between containers. In K8s, it works the **same way** through **Service DNS** — but it's more powerful because Services load-balance and survive pod restarts.

### 5.4 Create the Migration Planning Document

Create the file `k8s/migration-plan.md` in your project with this content:

```markdown
# DocuMind: Docker Compose → Kubernetes Migration Plan

## Migration Order (Dependency-Based)

### Phase 2 — Day 2: Stateless Backend
1. **FastAPI backend** → Deployment (2 replicas) + NodePort Service
   - Easiest starting point — no state, no volumes
   - Will temporarily hardcode env vars (fix in Phase 3)

### Phase 3 — Day 3: Message Queue Layer
2. **Redis** → Deployment + PVC + ConfigMap
   - Needed before Celery workers can start
3. **Celery workers** → Deployment (2 replicas)
   - Connects to Redis via K8s Service DNS

### Phase 4 — Day 4-5: Databases
4. **Qdrant** → StatefulSet + Headless Service + PVC (10Gi)
5. **Neo4j** → StatefulSet + Headless Service + PVC (10Gi + 1Gi logs)

### Phase 5 — Day 6: Networking & Remaining
6. **MinIO** → StatefulSet + PVC (20Gi) [if needed]
7. **Ollama** → StatefulSet + PVC (large, for model files)
8. **Ingress** → NGINX Ingress Controller for single entry point

## Network Dependencies (Service DNS)

```
User → Ingress → frontend-service → Frontend Pods

Frontend Pods → fastapi-service → FastAPI Pods
                                       ↓
                              redis-service → Redis Pod
                              neo4j-service → Neo4j Pod
                              qdrant-service → Qdrant Pod
                              ollama-service → Ollama Pod

Worker Pods → redis-service (broker)
            → neo4j-service, qdrant-service, ollama-service (tasks)
```

## Resource Budget

| Service | CPU Request | Memory Request | Storage |
|---------|------------|---------------|---------|
| FastAPI ×2 | 500m each | 512Mi each | — |
| Celery ×2 | 500m each | 512Mi each | — |
| Frontend ×1 | 100m | 128Mi | — |
| Redis ×1 | 250m | 256Mi | 2Gi |
| Qdrant ×1 | 500m | 512Mi | 10Gi |
| Neo4j ×1 | 500m | 1Gi | 11Gi |
| Ollama ×1 | 1000m | 2Gi | 20Gi |
| **Total** | **~4.5 CPU** | **~6Gi** | **43Gi** |
```

---

## Step 6: Enable the K8s Dashboard (Optional but Helpful)

The dashboard gives you a **visual UI** for everything kubectl shows in text:

```bash
# Enable the metrics server (needed for resource usage data)
minikube addons enable metrics-server

# Launch the dashboard (opens in your browser)
minikube dashboard
```

> **📖 What to explore in the dashboard:**
> - **Workloads → Pods** — see your running pods visually
> - **Cluster → Nodes** — see your minikube node's resources
> - **Config → Config Maps / Secrets** — see configuration objects
>
> The dashboard is great for learning because it shows the **relationships** between objects that kubectl shows in separate commands.

---

## ✅ Phase 1 Checklist

Run through this checklist to verify you're ready for Phase 2:

### Knowledge Check
- [ ] Can explain: "K8s declares desired state, controllers reconcile actual to desired"
- [ ] Know the difference between Control Plane and Worker Node
- [ ] Understand: Pod wraps containers, Deployment wraps Pods, Service routes to Pods
- [ ] Know why bare Pods are bad for production (no auto-restart)

### Hands-On Check
```bash
# 1. Cluster is running
kubectl get nodes
# Expected: minikube   Ready   control-plane

# 2. You're in the learning namespace
kubectl config view --minify | grep namespace
# Expected: namespace: learning

# 3. You can deploy and delete pods
kubectl run verify-test --image=nginx:latest
kubectl get pods
kubectl delete pod verify-test
```

### Project Check
- [ ] Directory `k8s/base/` exists
- [ ] Directory `k8s/practice/` exists
- [ ] `k8s/practice/test-pod.yaml` created and tested
- [ ] `k8s/migration-plan.md` created with DocuMind service analysis

---

## 🎓 What's New Since DocuMind (Concepts You Didn't Need Before)

| Concept | Your DocuMind Experience | K8s Adds |
|---------|------------------------|----------|
| **Declarative state** | `docker-compose up` (imperative) | `kubectl apply` — K8s continuously reconciles |
| **Self-healing** | Manual `docker-compose restart` | K8s auto-restarts crashed pods |
| **Resource limits** | Docker uses all available resources | K8s enforces CPU/memory budgets per pod |
| **Labels & Selectors** | Not needed in Compose | How Services find Pods, how you filter `kubectl get` |
| **Namespaces** | All containers share one space | Logical isolation between environments/teams |
| **Health probes** | `HEALTHCHECK` in Dockerfile (basic) | Liveness + Readiness probes (K8s acts on failures) |

---

**When you've completed all the checklist items, let me know and we'll start Phase 2 — migrating your FastAPI backend to Kubernetes!** 🚀
