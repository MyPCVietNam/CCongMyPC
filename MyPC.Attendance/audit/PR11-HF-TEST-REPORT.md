# PR11-HF Test Report

- **Date (Asia/Bangkok):** 2026-11-02
- **Base:** `7f9040556f29b1a7d44aa5b2014a453c8cc1026c`
- **Command:** `cd MyPC.Attendance && .venv/bin/python -m pytest tests/ -q`
- **Result:** **257 passed**
- **PR11 camera suite:** `tests/integration/test_pr11_camera_rtsp_hf.py` — 11 passed
- **Frontend:** `npm run build` — 1600 modules OK
- **Matrix:** `docs/PR11_HF_ACCEPTANCE_MATRIX.csv` — 31 PASS / 5 BLOCKED
- **Physical gates:** CAMERA_LAB / FACE_PILOT / EXIT / INSTALLER = **BLOCKED**


Final HEAD: `80ef426264f259d5857ab0df0ce33e064fc6b8d8`
Branch: `cursor/pr11-camera-rtsp-hf-83a8` (base `cursor/pr10-windows-auth-hf-83a8`)
ManagePullRequest unavailable this turn — open PR via GitHub UI if needed.
