#!/usr/bin/env bash
set -euo pipefail
BASE="${MYPC_BACKEND_BASE:-http://127.0.0.1:8765}"
curl -fsS "$BASE/api/v1/health" | tee /tmp/mypc-health.json
echo
echo "health_ok"
