# P02-USB-HF3 — PID ownership RCA (PR #27 in-place)

**Pre-fix tip:** `2fcb5bf05cd61d47be93cbfbbbbb62ec4e16bddc`

## Owner Windows (2026-11-07)

- Update/Preflight/Diagnose PASS; `CAPTURE_MAPPING_VERIFIED=true`; COM warnings=0.
- `-Mode Start`: launcher PID 24776; health HTTP 200; listener PID ≠ launcher → abort
  then misleading generic “did not become healthy” (ownership throw swallowed by `catch {}`).
- Read-only venv probe: launcher spawns `conhost.exe` + `python.exe` child; `LISTENERS=0`
  so prior 18878 owner was **not** proven linked to 24776.

## Root cause

`OwningProcess -eq $proc.Id` treats venv redirector PID as the only valid server.
Windows Python 3.12 venv often has the real interpreter as a child. Health regex also
accepted `startup_phase=FAIL` / `status=degraded`.

## Fix

- Accept `DIRECT` or `VERIFIED_DESCENDANT` (python.exe + uvicorn cmdline + PPID proof /
  session proof after redirector exit). Reject `conhost`, foreign, ambiguous listeners.
- Start PASS only for HTTP 200 + `status=ok` + `startup_phase=READY`.
- Persist `uvicorn.launch.json` (listener PID, creation time, nonce, relationship).
- Stop/Update re-validate meta; never kill unverified/foreign; specific
  `EXIT_LISTENER_OWNERSHIP` / `EXIT_FOREIGN_LISTENER` codes.
- Pure decision module: `scripts/windows/hf3_pid_ownership.py`.

USB frame / soak / CAMERA_LAB / FACE_PILOT / installer / production remain **BLOCKED**.
Healthy Start ≠ video frame received.
