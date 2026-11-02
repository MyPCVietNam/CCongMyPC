#!/usr/bin/env bash
# Fingerprint PR7 / corrective tip — does not claim tests passed.
set -euo pipefail
EXPECTED_PR7="81b9e949a5a30fba2159a47c208f3d6acdc1cdf8"
ROOT="$(git rev-parse --show-toplevel)"
ACTUAL="$(git rev-parse HEAD)"
BRANCH="$(git branch --show-current)"
printf 'root=%s\nbranch=%s\nhead=%s\nobserved_pr7_tip=%s\n' "$ROOT" "$BRANCH" "$ACTUAL" "$EXPECTED_PR7"
if [ "$BRANCH" = "cursor/mypc-attendance-p00-83a8" ]; then
  echo 'FAIL: P00 branch is NOT the PR7 application source (46≠155).'
  exit 5
fi
if [ "$ACTUAL" = "$EXPECTED_PR7" ] && [ "$BRANCH" = "cursor/pr6-followup-secure-pilot-83a8" ]; then
  echo 'PASS: Exact observed PR7 tip. This does NOT prove tests.'
  exit 0
fi
echo 'INFO: HEAD differs from observed PR7 snapshot — compare commits; preserve newer work.'
git log --oneline "$EXPECTED_PR7"..HEAD 2>/dev/null | head -20 || true
exit 0
