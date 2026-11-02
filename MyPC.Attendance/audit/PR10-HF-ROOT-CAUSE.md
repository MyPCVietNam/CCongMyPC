# PR10-HF Root Cause

**Baseline:** `f6719f0f91eaa48a3d0780f0cd8b06c46655abbe` (PR #10)  
**Branch:** `cursor/pr10-windows-auth-hf-83a8`

## AUTH

| ID | Cause | Fix |
|----|-------|-----|
| AUTH-01/09 | `App.tsx` ignored `must_change_password` | Dedicated `ChangePasswordPage`; gate before Layout/routes |
| AUTH-02 | `get_current_user` did not enforce pending flag | Path allowlist + 403 `MUST_CHANGE_PASSWORD`; `require_full_access` |
| AUTH-03/11 | Signed cookie only; logout cleared browser cookie | Durable `auth_sessions` + `User.auth_epoch`; logout/password revoke |
| AUTH-04 | First-run file deleted before durable commit | `pending_secret_cleanup` after `get_db` commit |
| AUTH-05 | Role frozen in cookie | Live role/epoch lookup; mismatch → 401 |
| AUTH-06 | `chmod 0600` only | Atomic write + Windows `icacls` owner-only best-effort |
| VISION-01 | Layout hardcoded `vi.mock` | `/api/v1/system/runtime-badge` server provenance |
| VISION-02 | `development` alone allowed mock ingest | Require `demo_mode` or `allow_mock_observation` |
| WIN-03 | OpenCV missing from requirements | Pin `opencv-contrib-python-headless==4.13.0.92` |
| WIN-01/04 | PS5.1 UTF-8 no BOM; wrong requirements path | UTF-8 BOM on all `.ps1`; `backend/requirements*.txt` + `npm.cmd` |

## Not defects (owner confusion)

- 401 on change-password = current password rejected; new password not applied.
- Multiple data profiles (`ProgramData` / `LocalAppData` / `./data`) each have their own first-run secret.
- TCP:554 reachable ≠ RTSP decode ≠ CAMERA_LAB PASS.
