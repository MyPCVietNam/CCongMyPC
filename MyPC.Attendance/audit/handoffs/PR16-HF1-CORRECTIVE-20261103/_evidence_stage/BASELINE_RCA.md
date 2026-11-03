# PR16-HF1 Baseline RCA (post-audit corrective)

**Baseline PR16 tip:** `1bdaef6a7aa63b24127239911fb021dcaf3e147a` (`cursor/pr16-realcam-stability-83a8`)  
**Branch:** `cursor/pr16-hf1-corrective-83a8`  
**Tree at branch create:** clean

## Independent audit findings → fixes

| ID | Finding | Fix |
|----|---------|-----|
| A1 | `testRtsp` + `runDiag` share `setDiag` → handshake overwritten | Separate handshake / legacy / LIVE lanes + retain on Kiểm tra |
| A2 | Camera page lacked per-camera health poll | 5s authenticated gateway health; cancel on switch/unmount; pause when hidden |
| A3 | MJPEG can freeze without `<img>.onError` | Decoder-health watchdog (`frame_age_ms` / STALE/RECONNECTING/DEGRADED) |
| A4 | `UNKNOWN` handshake clobbered DB status | UNKNOWN inconclusive — no clobber; AUTH/404 still persist |
| A5 | FPS window spans reconnect gaps | Reset `_recv_times` on reopen/disconnect; UNKNOWN until samples |
| A6 | OpenCV “FFMPEG” substring | Parse `FFMPEG: YES/NO` |
| A7 | Lab evidence lost on refresh | `GET .../quality/evidence` + UI load prior PHYSICAL |
| A8 | Secret auditor false orphans | Include archived + pending/processing/failed; UNKNOWN≠ORPHAN |
| A9 | No-op RTSP regression test | Real HTTP/DB assertions |
| A10 | CHANGED ZIP omitted handoff/docs | CHANGED-SOURCE-AUDIT includes all; CODE_PATHS vs HANDOFF_PATHS |

## Still BLOCKED (owner Windows)

LIVE_STABILITY_PASS · CAMERA_LAB_SIGNED · FACE_PILOT · INSTALLER · PRODUCTION_READY · native HEVC root cause
