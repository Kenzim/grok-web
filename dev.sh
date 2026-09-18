#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
# FastAPI BFF on :8787, Vite SPA on :5180 (proxies /api and /ws).
exec "$ROOT/.venv/bin/uvicorn" backend.app:app --host 127.0.0.1 --port 8787 --reload &
UVP=$!
trap 'kill "$UVP" 2>/dev/null || true' EXIT
cd "$ROOT/frontend"
npm run dev -- --host 127.0.0.1 --port 5180
