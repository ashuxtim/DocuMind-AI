#!/bin/bash

echo "🧠 Waking up AI..."
sudo systemctl start ollama

# Initialize defaults
export LLM_PROVIDER="ollama" 
export VLLM_BASE_URL=""
export OLLAMA_BASE_URL=""

# ==========================================
# 🔧 CONFIGURATION
# ==========================================
CLOUD_IP="164.52.193.213" 
SSH_KEY="~/.ssh/id_documind"
LOCAL_TUNNEL_PORT="8001"
LOCAL_OLLAMA_URL="http://localhost:11434"

# ==========================================
# 🧹 CLEANUP
# ==========================================
cleanup() {
    echo ""
    echo "🛑 Shutting down..."
    
    # Kill background log stream and processes
    if [ -n "$DOCKER_LOGS_PID" ]; then kill $DOCKER_LOGS_PID 2>/dev/null; fi
    if [ -n "$FRONTEND_PID" ]; then kill $FRONTEND_PID 2>/dev/null; fi
    if [ -n "$BACKEND_PID" ]; then kill $BACKEND_PID 2>/dev/null; fi
    
    if [ -n "$SSH_PID" ]; then
        kill $SSH_PID 2>/dev/null
        echo "🔌 SSH Tunnel Disconnected."
    fi

    echo "🐳 Stopping Infrastructure..."
    docker compose stop
    
    echo "✅ Cleanup complete."
    sudo systemctl stop ollama
    exit 0
}
trap cleanup SIGINT

# ==========================================
# 🔌 INTELLIGENT PROVIDER CHECK
# ==========================================
echo "----------------------------------------"
echo "   🔍 DETECTING AI RUNTIME"
echo "----------------------------------------"

if [ -f .env ]; then export $(grep -v '^#' .env | xargs); fi

if [ "$LLM_PROVIDER" == "gemini" ] || [ "$LLM_PROVIDER" == "openai" ]; then
    echo "💎 Explicit Provider Detected: $LLM_PROVIDER"
    MODE_LABEL="🌍 EXTERNAL API"
else
    echo "🤖 Checking hardware..."
    if ssh -q -o BatchMode=yes -o ConnectTimeout=3 -i $SSH_KEY root@$CLOUD_IP exit; then
        echo "✅ Cloud GPU Reachable."
        echo "🔗 Opening Tunnel (Port $LOCAL_TUNNEL_PORT -> Cloud 8000)..."
        ssh -N -i $SSH_KEY -L ${LOCAL_TUNNEL_PORT}:localhost:8000 root@$CLOUD_IP &
        SSH_PID=$!
        sleep 2
        export LLM_PROVIDER="vllm"
        export VLLM_BASE_URL="http://localhost:${LOCAL_TUNNEL_PORT}/v1"
        MODE_LABEL="☁️  CLOUD GPU (vLLM)"
    else
        echo "⚠️  Cloud unreachable. Switching to Local."
        export LLM_PROVIDER="ollama"
        export OLLAMA_BASE_URL="$LOCAL_OLLAMA_URL"
        MODE_LABEL="💻 LOCAL CPU (Ollama)"
    fi
fi

# ==========================================
# 🚀 HYBRID LAUNCH
# ==========================================
echo "----------------------------------------"
echo "   🚀 STARTING HYBRID STACK: $MODE_LABEL"
echo "----------------------------------------"

# 1. Start Infrastructure (Databases + Worker)
echo "📦 Spinning up Docker Infrastructure..."
docker compose up -d --build --remove-orphans redis neo4j qdrant worker

# --- NEW: STREAM DOCKER LOGS TO TERMINAL ---
# This makes the Worker logs visible!
echo "👀 Attaching to Docker logs (Worker, Neo4j, Redis)..."
docker compose logs -f -t &
DOCKER_LOGS_PID=$!

# 2. Start Frontend (Local)
echo "🎨 Starting Frontend (Vite)..."
cd frontend
npm run dev > /dev/null 2>&1 & # Silence frontend logs (too noisy)
FRONTEND_PID=$!
cd ..

# 3. Start Backend (Local)
echo "⚙️  Starting Backend (FastAPI)..."
echo "   (Hiding health-check spam, showing Errors & Uploads)"

# Activate Environment
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
pyenv activate documind-env

# Run from ROOT
# We use grep to filter out the annoying "GET / HTTP" polling logs
PYTHONPATH=./backend uvicorn main:app --reload 2>&1 | grep --line-buffered -v "GET / HTTP" &
BACKEND_PID=$!

# --- WAIT FOR READY STATE ---
echo "⏳ Waiting for Backend to come online..."
while ! curl -s http://localhost:8000/ > /dev/null; do
    sleep 1
done

echo ""
echo "============================================"
echo "   ✅ APPLICATION STARTUP COMPLETED"
echo "============================================"
echo "   👉 Frontend: http://localhost:5173"
echo "   👉 API Docs: http://localhost:8000/docs"
echo "============================================"
echo "   (Logs from Docker Worker & Local Backend are streaming below...)"

wait $FRONTEND_PID $BACKEND_PID $DOCKER_LOGS_PID