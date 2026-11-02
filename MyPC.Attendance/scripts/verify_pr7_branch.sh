#!/usr/bin/env bash
# Compatibility wrapper → strict PR8 checkout verify (fail-closed).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec bash "$ROOT/scripts/verify_pr8_checkout.sh"
