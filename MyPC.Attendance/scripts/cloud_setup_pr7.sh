#!/usr/bin/env bash
# Idempotent Cloud Agent setup for PR7+ corrective code under MyPC.Attendance.
# Never uses main (LICENSE-only) or P00 as the application source.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "== branch fingerprint =="
bash "$ROOT/scripts/verify_pr7_branch.sh" || true
git -C "$(git rev-parse --show-toplevel)" rev-parse HEAD > "$ROOT/audit/PR7-CLOUD-BRANCH-FINGERPRINT.txt"
git -C "$(git rev-parse --show-toplevel)" branch --show-current >> "$ROOT/audit/PR7-CLOUD-BRANCH-FINGERPRINT.txt"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
if [ -f backend/requirements.txt ]; then
  pip install -r backend/requirements.txt
elif [ -f requirements.txt ]; then
  pip install -r requirements.txt
fi
pip install pytest httpx
cd frontend
if [ -f package-lock.json ]; then npm ci; else npm install; fi
npm run build
cd "$ROOT"
echo "Setup OK. Start: bash scripts/cloud_start_pr7.sh"
