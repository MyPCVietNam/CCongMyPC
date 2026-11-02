#!/usr/bin/env bash
# Localhost-only FastAPI start. DEMO/MOCK provenance — not physical camera proof.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(git -C "$ROOT/.." rev-parse --show-toplevel 2>/dev/null || git rev-parse --show-toplevel)"
# Allow dirty during iterative coding; ancestry still required
MYPC_ALLOW_DIRTY_VERIFY=1 bash "$ROOT/scripts/verify_pr8_checkout.sh"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate
export MYPC_APP_ENV="${MYPC_APP_ENV:-development}"
export MYPC_DEMO_MODE="${MYPC_DEMO_MODE:-true}"
export MYPC_DATA_DIR="${MYPC_DATA_DIR:-$ROOT/data/cloud-dev}"
mkdir -p "$MYPC_DATA_DIR" runtime
HOST="${MYPC_HOST:-127.0.0.1}"
PORT="${MYPC_PORT:-8765}"
if [[ "$HOST" != "127.0.0.1" && "$HOST" != "localhost" ]]; then
  echo 'FAIL: Cloud start must bind localhost only (no 0.0.0.0)' >&2
  exit 30
fi
echo "head=$(git -C "$REPO" rev-parse HEAD)" > runtime/last-start.txt
echo "host=$HOST port=$PORT demo=$MYPC_DEMO_MODE" >> runtime/last-start.txt
echo "Starting MyPC Attendance on http://${HOST}:${PORT} (DEMO/MOCK — CAMERA_LAB BLOCKED)"
# Prefer PYTHONPATH over --app-dir (some uvicorn builds exit 1 after import with --app-dir).
export PYTHONPATH="$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"
exec python -m uvicorn app.main:app --host "$HOST" --port "$PORT"
