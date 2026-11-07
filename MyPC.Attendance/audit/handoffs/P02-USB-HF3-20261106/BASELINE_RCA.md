# Baseline RCA — PID safety corrective V2

## Owner Windows facts (do not reinterpret)

- PowerShell 5.1 + Python 3.12 venv redirector → child `python.exe` + `conhost.exe`.
- Prior HF3 Diagnose PASS (`CAPTURE_MAPPING_VERIFIED=true`, COM warning 0, model pins pass).
- Prior Start HTTP 200 failed strict launcher==listener equality (ownership V1 fixed that false-negative).
- Ownership V1 Stop/Update path introduced new safety defects on FULL SOURCE at tip `f441da4`.

## Independent static RED (5/5) on pre-fix tip

See `PID_SAFETY_BASELINE_RED.md`. Static tests ≠ Windows OS behavior proof.

## Root causes fixed

1. `$pid` foreach → automatic `$PID` read-only collision on PS 5.1.
2. Legacy pid-file Stop without creation-time proof (PID reuse hazard).
3. Optional blank `listener_creation` short-circuit.
4. Shared listener creation stamp applied to launcher PID list; no `launcher_creation`.
5. Folder/`uvicorn` substring as kill authorization.

## Non-goals

No Prepare; no 18876/18877; no DataDir/venv/model/HMAC wipe; no physical gate PASS from CI;
no automatic owner Start from GitHub Actions.
