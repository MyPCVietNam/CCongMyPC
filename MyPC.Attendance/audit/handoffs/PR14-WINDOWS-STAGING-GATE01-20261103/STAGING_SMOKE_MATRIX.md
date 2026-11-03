# Staging smoke matrix (Gate 01)

| # | Scenario | Cloud pinned | Windows owner |
|---|----------|--------------|---------------|
| 1 | Empty DataDir start → alembic_ok, HEAD 0012 | PASS | Retest |
| 2 | Second start same DataDir | PASS | Retest |
| 3 | Health: fastapi_supported=true | PASS | Capture screenshot/log |
| 4 | Synthetic upgrade 0008→0012 | PASS | — |
| 5 | Genuine clone upgrade counts preserved | BLOCKED (no prod copy here) | Required |
| 6 | Legacy DB without alembic_version refused | PASS | Retest optional |
| 7 | C13 promote disk-fault → HTTP 503 + code | PASS | Required on Windows service |
| 8 | Outbox retry → pending=0 | PASS | Required |
| 9 | C11 in-flight staged not scrubbed | PASS (pytest) | Smoke |
| 10 | C12 metadata+REPLACE | PASS (pytest) | Smoke |
| 11 | C14 lifecycle id reuse | PASS (pytest) | Smoke |
| 12 | EZVIZ LIVE decode | BLOCKED | CAMERA_LAB |
| 13 | Face match morning/afternoon | BLOCKED | FACE_PILOT |
| 14 | Installer MSI/service | BLOCKED | INSTALLER |
