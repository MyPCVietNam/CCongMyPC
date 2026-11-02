# PR10-HF Test Report

- **Date (Asia/Bangkok):** 2026-11-02
- **Baseline:** `f6719f0f91eaa48a3d0780f0cd8b06c46655abbe`
- **Platform (agent):** Linux cloud agent — native Windows PS5.1/hardware BLOCKED
- **Python:** 3.12.3
- **OpenCV:** 4.13.0 (`opencv-contrib-python-headless==4.13.0.92`) — FaceDetectorYN/SF True
- **Node:** v22.23.4

## Commands & results

| Suite | Command | Result |
|-------|---------|--------|
| Full pytest | `cd MyPC.Attendance && .venv/bin/python -m pytest tests/ -q` | **244 passed** |
| PR10 auth | `pytest tests/integration/test_pr10_auth_sessions.py` | 13 passed |
| Windows encoding/OpenCV | `pytest tests/unit/test_pr10_windows_encoding_and_opencv.py` | 5 passed |
| Frontend build | `cd frontend && npm ci && npm run build` | 1600 modules OK |
| npm audit | `npm audit --json` | 4 advisories captured (no force fix) |
| pip check | after OpenCV pin | PASS |
| Windows PS 5.1/7 parse | — | **BLOCKED** |
| CAMERA_LAB / FACE_PILOT / EXIT / INSTALLER | — | **BLOCKED** |

## Acceptance matrix

`docs/PR10_HF_ACCEPTANCE_MATRIX.csv` — 88 cases: 63 PASS / 25 BLOCKED (Windows owner / hardware).

## Frontend forced-change

Source: `ChangePasswordPage.tsx` + `App.tsx` gate. Build embeds Vietnamese copy. API deep-link to employees/cameras while pending → 403.
