# Owner helper notes for C13 on Windows.
# This script does NOT inject disk faults automatically (too environment-specific).
# It documents the exact assertions to capture after a manual/synthetic promote fault.
$ErrorActionPreference = 'Stop'
Write-Host @"
C13 Windows smoke
1) Use disposable DataDir clone + fake camera password only.
2) Login; create MOCK camera; note CSRF.
3) Trigger promote failure AFTER SQL commit (e.g. temporarily break secrets ACL
   or patch promote in a local debug build). Prefer a controlled lab hook —
   do not run against production.
4) Expect HTTP 503 and JSON detail.code == SECRET_FS_OUTBOX_INCOMPLETE.
5) Confirm outbox pending_count >= 1 (redacted diagnostics).
6) POST /api/v1/system/secret-fs-outbox/retry with SETTINGS_APPLY + CSRF
   OR restart service → pending_count == 0.
7) Save status/code only to owner-captured\C13_WIRE_RESPONSE_REDACTED.txt
   — strip cookies, tokens, passwords, Absolute DataDir paths if policy requires.
"@
