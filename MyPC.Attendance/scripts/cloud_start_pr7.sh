#!/usr/bin/env bash
# Start FastAPI on localhost only. Does not open camera LAN tunnels.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate
export MYPC_APP_ENV="${MYPC_APP_ENV:-development}"
export MYPC_DEMO_MODE="${MYPC_DEMO_MODE:-true}"
export MYPC_DATA_DIR="${MYPC_DATA_DIR:-$ROOT/data/cloud-dev}"
mkdir -p "$MYPC_DATA_DIR"
HOST="${MYPC_HOST:-127.0.0.1}"
PORT="${MYPC_PORT:-8765}"
echo "Starting MyPC Attendance on http://${HOST}:${PORT} (localhost bind)"
exec python -m uvicorn app.main:app --app-dir backend --host "$HOST" --port "$PORT"
