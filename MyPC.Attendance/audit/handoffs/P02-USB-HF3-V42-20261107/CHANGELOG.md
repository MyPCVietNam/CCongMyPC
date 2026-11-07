# HF3 V4.2 changelog

## Corrective (SECURITY_SENSITIVE + WINDOWS_HOST, mocked CI only)

### R9 — Prepare genuinely fresh-only
- Authorize before any `src` / `venv` / `models` / `DataDir` mutation.
- Pin FULL ZIP SHA256, models source, candidate root (refuse 18876/18877 / DataDir / HF1-HF2 aliases).
- Fail closed on TCP/CIM UNKNOWN, existing launch meta, unsafe `uvicorn.pid`, or existing `src`.
- Stage into `src-prepare-staging-*`; promote via rename only after TOCTOU recheck. Never wipe live `src` for Prepare idempotency.
- Exit codes: `EXIT_PREPARE_EXISTING_SOURCE`, `EXIT_PREPARE_PROCESS_UNKNOWN`, `EXIT_PREPARE_INPUT_INVALID`.

### R10 — PID record consistency on every lifecycle arm
- Shared `Get-Hf3PidRecordState` / `Test-Hf3PidRecord` (ABSENT / VALID / INVALID / MATCH / MISMATCH / LIVE_UNKNOWN / STALE_ABSENT).
- Start/Update/Stop require pid↔meta association when both exist; never silently overwrite conflicting pid.
- Safe archival of proven-stale meta; no kill on authorization failure.

### R11 — Python mirror listener name
- `classify_listener_ownership` DIRECT path requires `is_python_process(listener.name)`.
- Blank / null / conhost / non-python → `UNVERIFIED`.

### R12 — Production handler coverage
- `Invoke-Hf3PrepareHandler` / `Start` / `Update` / `Stop` live in candidate script.
- Injected harness extracts production functions + `Extract-ModeText`; OS side effects mocked; zero `Stop-Process` on negatives.

### Ancillary
- `Format-Hf3CreationStamp` normalizes ISO after `ConvertFrom-Json` DateTime promotion (PS Core / culture-safe compare).
