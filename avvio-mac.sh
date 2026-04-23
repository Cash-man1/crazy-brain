#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

BACKEND_PORT=8010
FRONTEND_PORT=5180

if [[ ! -f ".venv/bin/python" ]]; then
  echo "Esegui prima ./setup-mac.sh"
  exit 1
fi

if [[ ! -d "frontend/node_modules" ]]; then
  echo "Manca frontend/node_modules. Esegui prima ./setup-mac.sh"
  exit 1
fi

echo "VITE_API_URL=http://127.0.0.1:${BACKEND_PORT}" > "frontend/.env"

export ENVIRONMENT=development
export FRONTEND_URL=http://localhost:${FRONTEND_PORT}
export CORS_EXTRA_ORIGINS=http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT}
export PUBLIC_INGESTION_ENABLED=1
export LIVE_ROWS_FROM_REDIS=0
export REDIS_URL=
export SCRAPER_USE_EVOLUTION_API=1
export SCRAPER_PLAYWRIGHT_FALLBACK=1
export SCRAPER_CRONOLOGIA_HOURS=72
export PUBLIC_HISTORY_MAX_ITEMS=5000

echo "Avvio backend su http://127.0.0.1:${BACKEND_PORT} ..."
nohup bash -lc "cd '$ROOT_DIR' && source '.venv/bin/activate' && cd backend && python -m uvicorn main:app --reload --host 127.0.0.1 --port ${BACKEND_PORT}" > "$ROOT_DIR/backend.log" 2>&1 &
echo $! > "$ROOT_DIR/.backend.pid"

sleep 3

echo "Avvio frontend su http://localhost:${FRONTEND_PORT} ..."
nohup bash -lc "cd '$ROOT_DIR/frontend' && npm run dev -- --host 127.0.0.1 --port ${FRONTEND_PORT} --strictPort" > "$ROOT_DIR/frontend.log" 2>&1 &
echo $! > "$ROOT_DIR/.frontend.pid"

sleep 3

if command -v open >/dev/null 2>&1; then
  open "http://localhost:${FRONTEND_PORT}/dashboard" || true
fi

echo
echo "Avvio completato."
echo "Backend log:  $ROOT_DIR/backend.log"
echo "Frontend log: $ROOT_DIR/frontend.log"
echo "Per fermare tutto: ./chiudi-mac.sh"
