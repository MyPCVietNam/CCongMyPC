# MyPC Attendance — PR16-HF5 consolidated trust-chain closure

**Baseline (HF4 / PR #20):** `56660d0ddd7fb48883f6789400e28ab72a09825e`  
**Branch:** `cursor/pr16-hf5-trust-closure-83a8`  
**Download:** `MYPC-PR16-HF5-COMPLETE-AUDIT.zip` (A+B+C + manifests)

## Contents
- `CHANGED-SOURCE-AUDIT.zip` — all added/modified source + tests + handoff docs
- `FULL-SOURCE.zip` — complete tracked MyPC.Attendance tree (no DataDir/secrets/SQLite)
- `WINDOWS-SAFE-EVIDENCE.zip` — sanitized reports, versions, owner checklist
- Manifests: `SHA256SUMS*.txt`, `PACKAGE_META.json`, RCA, acceptance matrix, architecture

## Synthetic credentials in tests
Fixtures use disposable strings such as `SyntheticOldPass1!`, `SyntheticNewPass2!`, `TestAdminPass!234`. **Never** production camera secrets.

## Gates
- CODE_FIX: target PASS after pytest + frontend ci + nested ZIP scan
- Physical Windows / soak / HEVC / owner HMAC / FACE_PILOT / INSTALLER / production: **BLOCKED**

**Do not merge to main.**
