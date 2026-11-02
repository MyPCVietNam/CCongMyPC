# PR10-HF Changelog

- Alembic `20261102_0009`: `users.auth_epoch`, table `auth_sessions`.
- `auth_session_service` + deps/auth enforcement for pending password change and revocation.
- `ChangePasswordPage` + App/Login/Layout provenance badge wiring.
- `runtime-badge` API; mock ingest no longer silent in development.
- `opencv-contrib-python-headless==4.13.0.92` in `backend/requirements.txt`.
- Offline recovery + data profile inspect scripts.
- Windows scripts: UTF-8 BOM, `npm.cmd`, correct requirements paths, Readiness-PR10, Inspect helpers.
- Tests: `test_pr10_auth_sessions.py`, `test_pr10_windows_encoding_and_opencv.py`.
- Audit docs + Vietnamese Windows setup/recovery guide.
