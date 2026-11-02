# P02R Environment

## Commands (Cloud Agent)

See `docs/ENVIRONMENT_COMMANDS.md`.

| Step | Command | Result (this run) |
|------|---------|-------------------|
| Verify | `bash scripts/verify_pr8_checkout.sh` | PASS ancestry of `8c5b200…` |
| Setup | `bash scripts/cloud_setup_pr8.sh` | OK twice; tracked tree clean |
| Setup×2 | same | Idempotent (ENV05) |
| Start | `bash scripts/cloud_start_pr8.sh` | localhost `127.0.0.1:8765` DEMO/MOCK |
| Health | `bash scripts/cloud_health_pr8.sh` | HTTP 200 |
| Pytest | `.venv/bin/python -m pytest tests/ -q` | **205 passed** |
| Frontend | `cd frontend && npm run build` | OK |

## Fingerprint location

`MyPC.Attendance/runtime/source-fingerprint.txt` and `runtime/last-setup.txt` (gitignored).

## Explicit non-claims

Cloud DEMO/MOCK health ≠ CAMERA_LAB PASS. No company LAN EZVIZ from this environment.
