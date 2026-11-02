#!/usr/bin/env bash
# Fail-closed PR #8 source fingerprint. Exit nonzero on wrong/divergent source.
# Does NOT claim camera/tests PASS.
set -euo pipefail
PIN='8c5b20058e6777bb61666e541e8fa5ba65a770e9'
ALLOW_DIRTY="${MYPC_ALLOW_DIRTY_VERIFY:-0}"
if ! root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  echo 'FAIL NO_REPO: run from a MyPC Attendance Git working tree' >&2
  exit 10
fi
cd "$root"
head_sha="$(git rev-parse HEAD)"
branch="$(git branch --show-current || true)"
printf 'PR8_SOURCE_ROOT=%s\nPR8_SOURCE_BRANCH=%s\nPR8_SOURCE_HEAD=%s\nPR8_REQUIRED_ANCESTOR=%s\n' \
  "$root" "${branch:-DETACHED}" "$head_sha" "$PIN"
case "$branch" in
  main|master|cursor/mypc-attendance-p00-83a8)
    echo 'FAIL WRONG_BRANCH: main/P00 cannot validate PR8 (46≠167)' >&2
    exit 11
    ;;
esac
if ! git cat-file -e "${PIN}^{commit}" 2>/dev/null; then
  echo 'FAIL PIN_MISSING: fetch PR8 corrective branch first' >&2
  exit 12
fi
if ! git merge-base --is-ancestor "$PIN" HEAD; then
  echo 'FAIL WRONG_SOURCE: PR8 tip is not an ancestor of HEAD' >&2
  exit 13
fi
if [[ ! -f "$root/MyPC.Attendance/scripts/cloud_setup_pr7.sh" ]] && \
   [[ ! -f "$root/MyPC.Attendance/scripts/cloud_setup_pr8.sh" ]]; then
  echo 'FAIL APP_MISSING: expected MyPC.Attendance application tree' >&2
  exit 14
fi
if [[ "$ALLOW_DIRTY" != "1" ]]; then
  if ! git diff --quiet || ! git diff --cached --quiet; then
    echo 'FAIL DIRTY_TRACKED: review tracked WIP before trusted Environment snapshot' >&2
    git status --short | head -40 >&2
    exit 15
  fi
fi
runtime_dir="${MYPC_RUNTIME_DIR:-$root/MyPC.Attendance/runtime}"
mkdir -p "$runtime_dir"
{
  echo "head=$head_sha"
  echo "branch=${branch:-DETACHED}"
  echo "pin=$PIN"
  echo "checked_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$runtime_dir/source-fingerprint.txt"
printf 'PASS: PR8 corrective commit verified in ancestry. NOT a camera/test PASS.\n'
