#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -f ".venv/bin/python" ]]; then
  echo "Esegui prima ./setup-mac.sh"
  exit 1
fi

if [[ ! -d "frontend/node_modules" ]]; then
  echo "Manca frontend/node_modules. Esegui prima ./setup-mac.sh"
  exit 1
fi

if [[ ! -f "frontend/.env" ]]; then
  echo "VITE_API_URL=http://127.0.0.1:8000" > "frontend/.env"
fi

export ENVIRONMENT=development
export FRONTEND_URL=http://localhost:5173
export CORS_EXTRA_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
export PUBLIC_INGESTION_ENABLED=1
export LIVE_ROWS_FROM_REDIS=0
export REDIS_URL=
export SCRAPER_USE_EVOLUTION_API=1
export SCRAPER_PLAYWRIGHT_FALLBACK=1
export SCRAPER_CRONOLOGIA_HOURS=72
export PUBLIC_HISTORY_MAX_ITEMS=5000

echo "Avvio backend su http://127.0.0.1:8000 ..."
nohup bash -lc "cd '$ROOT_DIR' && source '.venv/bin/activate' && cd backend && python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000" > "$ROOT_DIR/backend.log" 2>&1 &
echo $! > "$ROOT_DIR/.backend.pid"

sleep 3

echo "Avvio frontend su http://localhost:5173 ..."
nohup bash -lc "cd '$ROOT_DIR/frontend' && npm run dev" > "$ROOT_DIR/frontend.log" 2>&1 &
echo $! > "$ROOT_DIR/.frontend.pid"

sleep 3

if command -v open >/dev/null 2>&1; then
  open "http://localhost:5173/dashboard" || true
fi

echo
echo "Avvio completato."
echo "Backend log:  $ROOT_DIR/backend.log"
echo "Frontend log: $ROOT_DIR/frontend.log"
echo "Per fermare tutto: ./chiudi-mac.sh"
