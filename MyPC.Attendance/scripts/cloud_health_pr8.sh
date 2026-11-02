#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${MYPC_BACKEND_BASE:-http://127.0.0.1:8765}"
mkdir -p "$ROOT/runtime"
code="$(curl -sS -o "$ROOT/runtime/last-health.json" -w '%{http_code}' "$BASE/api/v1/health" || true)"
if [[ "$code" != "200" ]]; then
  echo "FAIL HEALTH_HTTP=$code" >&2
  exit 40
fi
echo "health_http=$code"
cat "$ROOT/runtime/last-health.json"
echo
echo "NOTE: health OK ≠ CAMERA_LAB PASS"
