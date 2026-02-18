#!/bin/bash
# setup_env.sh

echo "📦 Installing System Dependencies (for Unstructured & Redis)..."
sudo apt-get update
sudo apt-get install -y libmagic-dev poppler-utils tesseract-ocr libreoffice pandoc redis-tools

echo "🐍 Installing Python Dependencies..."
# Ensure you are inside your virtualenv before running this!
pip install -r backend/requirements.txt
pip install celery[redis] watchdog

echo "🐳 Starting Infrastructure (Redis & Neo4j)..."
# Start Redis (if not running)
docker run -d --name documind-redis -p 6379:6379 redis:alpine 2>/dev/null || docker start documind-redis

# Ensure Neo4j is running
docker start documind-graph 2>/dev/null

echo "✅ Environment Ready!"