# Environment commands — PR #9 / P02S

PR #9 full tip: `3bd84dfb4dc779bb2c1709b2bd04bbc8843c7f87`
PR8 ancestry alone is **not** enough for P02S.

## Setup

```bash
cd "$(git rev-parse --show-toplevel)"
git status --porcelain=v1
git branch --show-current
git rev-parse HEAD
git merge-base --is-ancestor 3bd84dfb4dc779bb2c1709b2bd04bbc8843c7f87 HEAD || exit 1
cd MyPC.Attendance
bash scripts/verify_pr9_checkout.sh
bash scripts/cloud_setup_pr9.sh
.venv/bin/python -m pytest tests/ -q
(cd frontend && npm run build)
```

## Startup (separate session)

```bash
cd "$(git rev-parse --show-toplevel)/MyPC.Attendance"
MYPC_APP_ENV=development MYPC_DEMO_MODE=true MYPC_HOST=127.0.0.1 MYPC_PORT=8765 \
  bash scripts/cloud_start_pr9.sh
```

## Health

```bash
cd "$(git rev-parse --show-toplevel)/MyPC.Attendance"
bash scripts/cloud_health_pr9.sh
```

Health HTTP 200 ≠ CAMERA_LAB / FACE_PILOT / INSTALLER PASS.
