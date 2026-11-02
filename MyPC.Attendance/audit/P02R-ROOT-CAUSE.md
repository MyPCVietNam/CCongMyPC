# P02R Root Cause

## Base

- PR #8 corrective commit: `8c5b20058e6777bb61666e541e8fa5ba65a770e9`
- Feature branch: `cursor/pr8-p02r-winlab-readiness-83a8`

## Issues closed in this phase

1. **Cloud Environment false confidence** — `cloud_setup_pr7.sh` previously could ignore verify (`|| true`); `verify_pr7_branch.sh` could INFO-exit on divergent tips and pin PR7 instead of requiring PR8 ancestry. Fixed with fail-closed `verify_pr8_checkout.sh` + `cloud_{setup,start,health}_pr8.sh` (pr7 wrappers exec pr8). Fingerprints go to ignored `runtime/` only.

2. **PHYSICAL_VERIFIED truth gap** — `/evidence/record` could accept client `labeled_known/unknown` + health W/H as physical. Replaced with lab-run FSM: `CREATED → LIVE_MEASURED → OWNER_REVIEWED → PHYSICAL_VERIFIED` via server-measured LIVE frames, one-time owner challenge, and FACE_PILOT server case events. Direct PHYSICAL via `/evidence/record` returns `NEED_LAB_RUN_PROMOTE`.

3. **uvicorn `--app-dir` startup** — on this Cloud image, `python -m uvicorn ... --app-dir backend` exited 1 after Alembic without binding. Start scripts now set `PYTHONPATH=backend`.

## Remaining (by design)

- CAMERA_LAB / FACE_PILOT / EXIT_VERIFICATION / INSTALLER remain **BLOCKED** until genuine Windows LAN EZVIZ evidence.
- No merge to `main`.
