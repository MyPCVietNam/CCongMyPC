# P01.5 Camera Readiness

| Item | Status |
|------|--------|
| Camera model | EZVIZ CS-H8-R100-1J5WKFL (H8 Pro 3K), FW V5.3.8 build 240329 (reported) |
| LAN/IP known | Yes (operator-side) |
| ONVIF on Windows | **BLOCKED** — not verified in this agent run |
| RTSP native decode | **BLOCKED** |
| Timestamp handling | **BLOCKED** |
| Illumination / face px at door | **BLOCKED** |
| Live enrollment REAL_CAMERA API | Returns `CAMERA_LAB_BLOCKED` (503) by design |
| DEMO / UPLOAD / fixture | Available for non-production tests |
| Non-biometric attendance fallback | Preserved (P00 rules unchanged) |

**Gate verdict:** `CAMERA_LAB = BLOCKED`, `FACE_PILOT = BLOCKED`, `WINDOWS_RUNTIME = BLOCKED` until evidenced on the company Windows computer. Mock/REPLAY success must never be labeled CAMERA_LAB_PASS or FACE_PILOT_PASS.
