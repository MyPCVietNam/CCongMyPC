#!/usr/bin/env bash
# Compatibility wrapper → strict PR8 setup (fail-closed ancestry).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec bash "$ROOT/scripts/cloud_setup_pr8.sh"
