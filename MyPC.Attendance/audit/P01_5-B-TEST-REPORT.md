# MyPC Attendance — P01.5-B/C Test Report (Auto Enrollment + Body Reference)

**Date:** 2026-11-02 (Asia/Saigon)  
**Branch:** `cursor/p01-5-auto-enrollment-83a8`

## Implemented

- Guided auto session APIs under `/api/v1/employees/{id}/enrollment/auto/*`
- Full-frame scanning; **no mandatory ROI**
- Face slots: FACE_FRONT, FACE_LEFT, FACE_RIGHT with Vietnamese guidance and announcements
- Body reference slots: BODY_FRONT/LEFT/RIGHT/MOTION — labeled supporting evidence only (not biometric ID)
- Multiple people → PAUSE; duplicate frames rejected; identity consistency across face slots
- Independent verification required before ACTIVE
- Honest `BLOCKED_BY_CAMERA_GEOMETRY` / `BODY_CAPTURE_BLOCKED` when declared or quality fails
- Person detector: synthetic geometry placeholder; YOLOX-Nano **not** bundled yet (license/hash pending) — Ultralytics AGPL avoided
- Vietnamese EnrollmentPage UI: progress tiles, pause/resume/retry/cancel/activate, optional speech/beep

## Tests

| Case | Result |
|------|--------|
| Full DEMO auto flow 3 face + 4 body → activate → MATCH | PASS |
| REAL_CAMERA auto start blocked (CAMERA_LAB_BLOCKED) | PASS |
| Body geometry blocked honest | PASS |
| Duplicate frame rejected | PASS |
| Frontend `npm run build` | PASS |

## Gates

| Gate | Status |
|------|--------|
| FACE_POSE_CAPTURE | PASS (DEMO/synthetic + API); physical **BLOCKED** |
| BODY_REFERENCE_CAPTURE | PASS (DEMO geometry); real EZVIZ likely **BLOCKED_BY_CAMERA_GEOMETRY** until lab |
| IDENTITY_CONFLICT | PASS (collision path + best-by-identity margin) |
| FRONTEND_BUILD | PASS |
| CAMERA_LAB / FACE_PILOT / WINDOWS_RUNTIME / INSTALLER | **BLOCKED** |

## Blockers

1. High-angle EZVIZ shop view may not yield head-to-feet ≥400 px and large face at one position — app fails honestly; alternate supervised position supported by process, not ROI drawing
2. YOLOX-Nano weights not yet hash-pinned/bundled — body boxes use synthetic detector in DEMO only
3. Live camera preview WebSocket/SSE is polling snapshot only; REAL_CAMERA still 503
