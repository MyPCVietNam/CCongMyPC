# P00-HF REPORT — Security hardening

**Baseline SHA:** `faf23d2f9b0d75c48aac033d3c55552fca9d35fa`  
**Phase:** P00-HF  
**Spec:** v1.5  

## Fixes implemented

| Finding | Fix | Module |
|---------|-----|--------|
| A Mock observation open in production | Gated by `app_env`/`demo_mode`/`allow_mock_observation` + `DEMO_MOCK_INGEST` | `api/attendance.py`, `core/settings.py` |
| B Camera CRUD without CAMERA_MANAGE | `require_permission(CAMERA_MANAGE)` + ROI/SSRF validation | `api/cameras.py`, `core/validation.py` |
| C Silent mock preview on live fail | Returns `503 LIVE_NOT_IMPLEMENTED` — no substitute | `api/cameras.py`, `vision/mock_camera.py` |
| D Tautological assert | Real exact/non-exact stamp assertions | `domain/afternoon_selection.py` |
| E CSRF by user id | CSRF bound to `sid` in session token | `api/deps.py`, `api/auth.py` |
| F First-run password file | 0o600 ACL helper + change-password wipes file | `services/bootstrap.py`, `api/auth.py` |
| G Migrations | Alembic `20261102_0001` + create_all bootstrap | `backend/alembic/` |
| H Idempotency | `idempotency_key` unique on raw_observations | `services/attendance_service.py`, models |
| I ONVIF catalog ≠ PASS | Unchanged BLOCKED lab semantics + Windows scripts | `scripts/windows/`, docs/vi |

## Tests

`pytest tests/unit tests/integration` — see P01-TEST-REPORT for combined totals including HF cases in `tests/integration/test_p00_hf_security.py`.

## Gates

| Gate | Status |
|------|--------|
| SOURCE_CUSTODY | PASS |
| P00_SECURITY | PASS (automated) |
| WINDOWS_RUNTIME | BLOCKED (Linux agent) |
| CAMERA_LAB | BLOCKED |
| INSTALLER_BUILD | BLOCKED |
