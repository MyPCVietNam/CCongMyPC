# P02 acceptance matrix

| Item | Result |
|------|--------|
| Detect on registry CAMERA_LIVE (no 2nd capture) | PASS (code) |
| Opt-in mjpeg-ai 1–3 AI FPS; original mjpeg unchanged | PASS |
| MOCK / STALE / NOT_READY / NO_FACE / MULTIPLE / TOO_SMALL / OUTSIDE_ROI | PASS |
| Frame_id aligned boxes; clone-before-draw | PASS |
| GET regions loads DB ROI; draft before save | PASS |
| ROI save does not revoke CAMERA_LAB HMAC | PASS |
| No attendance writes / no identity in overlay | PASS |
| pytest 410 / vitest 13 / typecheck / vite build | PASS |
| Physical soak / LIVE_STABILITY / FACE_PILOT / installer / production | **BLOCKED** |
