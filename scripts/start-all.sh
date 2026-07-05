#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "🚀 BkAI full stack startup"

bash "$ROOT/scripts/start-infra.sh"

echo ""
echo "⏳ Ingest (skip if Qdrant already populated):"
echo "   cd backend && source .venv/bin/activate && python ingest.py"
echo ""

echo "🔧 Starting backend on :8000 ..."
cd "$ROOT/backend"
source .venv/bin/activate
python main.py &
BACKEND_PID=$!

echo "🎨 Starting frontend on :5173 ..."
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ Backend PID:  $BACKEND_PID  → http://localhost:8000"
echo "✅ Frontend PID: $FRONTEND_PID → http://localhost:5173"
echo "   Chat:       http://localhost:5173/"
echo "   Voice:      http://localhost:5173/voice"
echo "   Dashboard:  http://localhost:5173/dashboard"
echo ""
echo "Press Ctrl+C to stop."

wait
