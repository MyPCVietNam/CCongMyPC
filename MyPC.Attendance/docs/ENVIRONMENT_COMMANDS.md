# Cursor Cloud Environment: verified PR #8 setup/start/health

## Pin

- PR #8 corrective commit: `8c5b20058e6777bb61666e541e8fa5ba65a770e9`
- Feature work must be a descendant of that commit.
- Never use `main` or P00 (46-test tip) for this app.

## Environment Setup command

```bash
cd "$(git rev-parse --show-toplevel)"
git status --porcelain=v1
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor 8c5b20058e6777bb61666e541e8fa5ba65a770e9 HEAD
cd MyPC.Attendance
bash scripts/cloud_setup_pr8.sh
.venv/bin/python -m pytest tests/ -q
(cd frontend && npm run build)
```

`cloud_setup_pr7.sh` is a fail-closed wrapper that execs `cloud_setup_pr8.sh`.
Fingerprint is written to ignored `MyPC.Attendance/runtime/` only.

## Startup command (separate session)

```bash
cd "$(git rev-parse --show-toplevel)/MyPC.Attendance"
MYPC_APP_ENV=development MYPC_DEMO_MODE=true MYPC_HOST=127.0.0.1 MYPC_PORT=8765 \
  bash scripts/cloud_start_pr8.sh
```

## Health check command

```bash
cd "$(git rev-parse --show-toplevel)/MyPC.Attendance"
bash scripts/cloud_health_pr8.sh
```

Confirm HTTP 200 at `http://127.0.0.1:8765/api/v1/health`.
Health OK ≠ CAMERA_LAB / FACE_PILOT PASS. Cloud has no company LAN EZVIZ.
