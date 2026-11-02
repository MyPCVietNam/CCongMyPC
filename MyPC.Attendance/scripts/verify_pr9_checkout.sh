#!/usr/bin/env bash
# Fail-closed PR #9 (P02R tip) ancestry. Exit nonzero on wrong/divergent source.
# PR8 ancestry alone is NOT enough for P02S.
set -euo pipefail
PIN_PR9='3bd84dfb4dc779bb2c1709b2bd04bbc8843c7f87'
PIN_PR8='8c5b20058e6777bb61666e541e8fa5ba65a770e9'
ALLOW_DIRTY="${MYPC_ALLOW_DIRTY_VERIFY:-0}"
if ! root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  echo 'FAIL NO_REPO: run from a MyPC Attendance Git working tree' >&2
  exit 10
fi
cd "$root"
head_sha="$(git rev-parse HEAD)"
branch="$(git branch --show-current || true)"
printf 'PR9_SOURCE_ROOT=%s\nPR9_SOURCE_BRANCH=%s\nPR9_SOURCE_HEAD=%s\nPR9_REQUIRED_ANCESTOR=%s\n' \
  "$root" "${branch:-DETACHED}" "$head_sha" "$PIN_PR9"
case "$branch" in
  main|master|cursor/mypc-attendance-p00-83a8)
    echo 'FAIL WRONG_BRANCH: main/P00 cannot validate PR9/P02S' >&2
    exit 11
    ;;
esac
if ! git cat-file -e "${PIN_PR9}^{commit}" 2>/dev/null; then
  echo 'FAIL PIN_MISSING: fetch PR9 tip first' >&2
  exit 12
fi
if ! git merge-base --is-ancestor "$PIN_PR9" HEAD; then
  echo 'FAIL WRONG_SOURCE: PR9 tip is not an ancestor of HEAD (PR8-only is insufficient)' >&2
  exit 13
fi
if ! git merge-base --is-ancestor "$PIN_PR8" HEAD; then
  echo 'FAIL MISSING_PR8: historical PR8 ancestor also required' >&2
  exit 16
fi
if [[ ! -f "$root/MyPC.Attendance/scripts/cloud_setup_pr8.sh" ]] && \
   [[ ! -f "$root/MyPC.Attendance/scripts/cloud_setup_pr9.sh" ]]; then
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
  echo "pin_pr9=$PIN_PR9"
  echo "pin_pr8=$PIN_PR8"
  echo "checked_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "phase=P02S"
} > "$runtime_dir/source-fingerprint-pr9.txt"
printf 'PASS: PR9 tip verified in ancestry (and PR8). NOT a camera/test PASS.\n'
