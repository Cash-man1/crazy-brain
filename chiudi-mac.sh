#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "Chiusura Crazy Brain (macOS)..."

stop_pid_file() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file" || true)"
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
      echo "Terminato PID $pid"
    fi
    rm -f "$pid_file"
  fi
}

stop_pid_file "$ROOT_DIR/.backend.pid"
stop_pid_file "$ROOT_DIR/.frontend.pid"

# Fallback su processi rimasti in ascolto sulle porte note
for port in 8000 5173; do
  pids="$(lsof -ti tcp:$port || true)"
  if [[ -n "$pids" ]]; then
    echo "$pids" | xargs kill -9 2>/dev/null || true
    echo "Liberata porta $port"
  fi
done

echo "Chiusura completata."
