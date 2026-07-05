#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "🚀 Starting BkAI infrastructure..."

if ! docker info >/dev/null 2>&1; then
  echo "❌ Docker is not running. Please start Docker Desktop first."
  exit 1
fi

docker rm -f bkai-qdrant bkai-redis-stack 2>/dev/null || true

docker run -d --name bkai-qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v "$ROOT/backend/.qdrant:/qdrant/storage" \
  qdrant/qdrant:latest

docker run -d --name bkai-redis-stack \
  -p 6380:6379 \
  redis/redis-stack-server:latest

echo "✅ Qdrant:    http://localhost:6333"
echo "✅ Redis Stack: redis://localhost:6380"
echo ""
echo "Next:"
echo "  cd backend && source .venv/bin/activate && pip install pypdf python-docx -q && python ingest.py"
echo "  python main.py"
echo "  cd frontend && npm run dev"
