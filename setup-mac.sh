#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "============================================"
echo " Crazy Brain - setup desktop (macOS)"
echo "============================================"
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERRORE: python3 non trovato. Installa Python 3.10+."
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "ERRORE: node non trovato. Installa Node.js LTS."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "ERRORE: npm non trovato. Reinstalla Node.js."
  exit 1
fi

if [[ ! -f ".venv/bin/python" ]]; then
  echo "Creo ambiente virtuale Python (.venv)..."
  python3 -m venv .venv
fi

source ".venv/bin/activate"
python -m pip install --upgrade pip

echo "Installo dipendenze backend..."
pip install -r "backend/requirements.txt"

echo "Installo Chromium per Playwright (fallback)..."
(
  cd backend
  python -m playwright install chromium || {
    echo "ATTENZIONE: installazione Chromium fallita, continuo comunque."
  }
)

echo "Installo dipendenze frontend..."
(
  cd frontend
  if [[ ! -d "node_modules" ]]; then
    npm ci
  else
    echo "node_modules gia presente, salto npm ci."
  fi
)

if [[ ! -f "backend/.env" && -f "backend/.env.example" ]]; then
  cp "backend/.env.example" "backend/.env"
  echo "Creato backend/.env da backend/.env.example"
fi

if [[ ! -f "frontend/.env" ]]; then
  echo "VITE_API_URL=http://127.0.0.1:8000" > "frontend/.env"
  echo "Creato frontend/.env"
fi

echo
echo "Setup completato."
echo "Avvio rapido: ./avvio-mac.sh"
