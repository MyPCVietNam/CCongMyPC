# P02 CHANGELOG — REAL face overlay

- `LiveFaceDetectPreviewService`: shared per-camera YuNet detect+quality cache (1–3 AI FPS); rejects MOCK/STALE/non-REAL; no identity/attendance.
- `GET /api/v1/cameras/{id}/live/face-detect` (CAMERA_MANAGE): JSON boxes + quality + enrollment_gate.
- `GET /api/v1/cameras/{id}/preview/mjpeg-ai`: opt-in annotated MJPEG; original `/preview/mjpeg` unchanged.
- `GET /api/v1/cameras/{id}/regions`: load saved arrival ROI (UI no longer silently invents DB values).
- ROI PUT: bumps calibration_version; does **not** revoke CAMERA_LAB HMAC / rotate config_revision.
- `annotate_detection_bgr`: clone-before-draw.
- CameraPage: AI overlay toggle (default off), draft ROI SVG, discrete readiness lanes (a–f), Vietnamese labels.
- `frontend/src/camera/imageCoords.ts` + Vitest contain/letterbox math.
- Static bundle refresh (`index-9TtdYGpe.js`).
