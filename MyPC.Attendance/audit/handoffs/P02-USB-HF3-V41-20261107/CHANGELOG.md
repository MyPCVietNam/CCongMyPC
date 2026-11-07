# HF3 PID Safety V4.1 — residual fail-closed corrective

Baseline RED tip: `7c6a324` (V4 packaged HEAD). Independent canaries R1–R8 failed on unchanged V4.

## Fixes
1. **R1/R2** `Validate-Hf3LaunchMetaBeforeCleanup` — parseable foreign/incomplete schema cannot authorize Start cleanup or Update source swap.
2. **R3** Stop no-listener probes saved `listener_pid`+creation; `EXIT_STOP_STALE_LISTENER` preserves evidence (no numeric kill).
3. **R4** Update free-port + absent meta checks legacy `uvicorn.pid` (live/UNKNOWN/unreadable → block).
4. **R5** `Test-Hf3TcpEmptyQueryError` — ObjectNotFound + exact empty MSFT prefix only; timeout/access with tempting substrings → `EXIT_TCP_PROBE_UNKNOWN`.
5. **R6** Python `kill_authorized` requires `is_python` for listener (mirrors PS).
6. **R7** Injected harness runs `Invoke-Hf3StartHandler` / `Update` / `Stop` with mocked side effects.
7. **R8** Update decision foreach never calls `Stop-VerifiedHf3Identity`; any LIVE_MATCH refuses swap.

Physical gates remain BLOCKED. Verdict: READY_FOR_INDEPENDENT_REAUDIT only.
