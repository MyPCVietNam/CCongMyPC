# HF3 PID Safety Corrective — technical rationale (English)

## Problem

PR #27 tip `f441da4` fixed the Start false-negative when a Windows Python 3.12 venv
redirector spawns a child `python.exe` listener (DIRECT / VERIFIED_DESCENDANT). Owner
Windows evidence showed parent→child spawning; prior HF3 Diagnose PASS is unchanged.
That ownership patch still left Stop/Update/failure-cleanup unsafe on PowerShell 5.1.

## Fixes (behavioral contract)

1. **No `$PID` assignment.** Kill helpers use `$TargetPid` / role-scoped params only.
2. **Fail-closed legacy Stop.** `uvicorn.pid` without `uvicorn.launch.json` →
   `EXIT_STOP_BLOCKED_LEGACY_PID`; evidence files preserved; no kill.
3. **Creation timestamps required.** Schema and `Test-LiveMatchesLaunchMeta` refuse
   blank/mismatched `listener_creation`. Separate `launcher_creation` persisted on Start;
   launcher kill refused without it.
4. **Per-PID identity kill.** `Stop-VerifiedHf3Identity` requires PID + creation + role
   proof (listener: uvicorn tokens + backend/port; launcher: python + expected exe path).
   No candidate-folder / `uvicorn` substring authorization. Never kill `conhost.exe`.
5. **Preserve meta on refusal.** Foreign/ambiguous/incomplete Stop keeps `uvicorn.launch.json`
   / pid file. Success only when port 18878 has no listener after verified stop.
6. **Update order.** SHA256 + staged backend layout validated before any owned stop;
   same-parent leaf `Rename-Item` + rollback; DataDir/venv/models/HMAC/18876/18877 untouched.
7. **Health.** HTTP 200 + top-level JSON `status=="ok"` and `startup_phase=="READY"` only
   (`ConvertFrom-Json`); ownership exceptions are not swallowed as generic health errors.
8. **Cmdline tokens.** Require `-m uvicorn`, `app.main:app`, `--host`, `--port`, `--app-dir`
   with exact backend path — not free-form substrings.

COM CoInit / VT_BSTR / exactly-once ownership / VID·PID·MI identity / PnP↔DShow mapping
unchanged. Physical gates remain BLOCKED until owner evidence.
