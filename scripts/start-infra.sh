#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Starting BkAI infrastructure (Redis Stack)..."

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. Start Docker Desktop first."
  exit 1
fi

# Prefer existing compose service name; fall back to a standalone container.
if docker compose -f "$ROOT/docker-compose.yml" ps --status running 2>/dev/null | grep -q bkai-redis; then
  echo "bkai-redis already running via docker compose"
elif docker start bkai-redis >/dev/null 2>&1; then
  echo "Started existing container: bkai-redis"
else
  docker rm -f bkai-redis bkai-redis-stack local-redis 2>/dev/null || true
  docker run -d --name bkai-redis -p 6380:6379 redis/redis-stack-server:latest
  echo "Created bkai-redis on localhost:6380"
fi

echo "Redis Stack: redis://localhost:6380"
echo ""
echo "Next:"
echo "  cd backend && source .venv/bin/activate && python ingest.py   # ChromaDB + BM25"
echo "  python main.py"
echo "  cd frontend && npm run dev"
