#!/usr/bin/env bash
# Idempotent Cloud Agent setup — PR8 ancestry required; fingerprint to runtime/ only.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(git -C "$ROOT/.." rev-parse --show-toplevel 2>/dev/null || git rev-parse --show-toplevel)"
cd "$REPO"
bash "$ROOT/scripts/verify_pr8_checkout.sh"
cd "$ROOT"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
if [ -f backend/requirements.txt ]; then
  pip install -r backend/requirements.txt
elif [ -f requirements.txt ]; then
  pip install -r requirements.txt
else
  echo 'FAIL: no requirements.txt' >&2
  exit 20
fi
pip install pytest httpx
cd frontend
if [ -f package-lock.json ]; then npm ci; else npm install; fi
npm run build
cd "$ROOT"
mkdir -p runtime
{
  echo "setup_head=$(git -C "$REPO" rev-parse HEAD)"
  echo "setup_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > runtime/last-setup.txt
# Must not modify tracked files
cd "$REPO"
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo 'FAIL SETUP_TRACKED_CHANGED: setup must not edit tracked source/audit' >&2
  git status --short | head -40 >&2
  exit 22
fi
echo "Setup OK. Start: bash scripts/cloud_start_pr8.sh"
echo "Physical CAMERA_LAB/FACE_PILOT remain BLOCKED on Cloud."
