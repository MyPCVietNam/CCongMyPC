# PR16 acceptance matrix

| Gate | Result | Notes |
|------|--------|-------|
| CODE_FIX_PASS | PASS (cloud) | 305 pytest; handshake/LIVE honesty; telemetry |
| WINDOWS_TEST_PASS | OWNER | Re-run LIVE create + 15–30 min soak |
| LIVE_STABILITY_PASS | BLOCKED | Needs owner soak evidence |
| PHYSICAL_VERIFIED | OWNER prior | Exists on staging per owner; not re-proven here |
| CAMERA_LAB_SIGNED | BLOCKED | HMAC UI added; owner must sign + verify |
| FACE_PILOT_PASS | BLOCKED | Independent |
| PRODUCTION_READY | HOLD | No main merge |

| Software fix | Result |
|--------------|--------|
| S1 MOCK badge stale | CODE_FIX_PASS |
| S2 RTSP clobber LIVE meaning | CODE_FIX_PASS |
| S4 HEVC telemetry honesty | CODE_FIX_PASS (native UNAVAILABLE) |
| S5 corrupt hot-loop | CODE_FIX_PASS |
| S6 preview during reconnect | CODE_FIX_PASS |
| S7 HMAC UI missing | CODE_FIX_PASS (UI); SIGNED=BLOCKED |
| S8 secret count opacity | CODE_FIX_PASS (read-only tool) |
