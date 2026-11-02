# PR11 RealCam Reliability — test report

**Branch:** `cursor/pr11-realcam-reliability-83a8`  
**Base:** `cursor/pr11-secret-acl-hf-83a8` @ `729fb6acd69cd4dcd328cc919260a1931efef11d`  
**Do not merge into main.**

## Linux CI

| Suite | Result |
|-------|--------|
| Full pytest | **282 passed** |
| RealCam unit/integration | PASS |
| Prior camera/lab/secrets tests | PASS |

## Windows / physical gates

| Gate | Status |
|------|--------|
| CAMERA_LAB | **BLOCKED** |
| FACE_PILOT | **BLOCKED** |
| EXIT_VERIFICATION | **BLOCKED** |
| INSTALLER | **BLOCKED** |
| H8 Pro 30‑min sequential stability (TCP/H265/H264/Wi‑Fi/RJ45) | **BLOCKED** — owner |

## Implemented (summary)

- HEVC/corrupt-frame guard, keyframe warmup, backoff+jitter, DEGRADED status, metrics
- One LIVE decoder lease per physical stream fingerprint; 409 if another camera holds it
- Authenticated MJPEG LIVE preview + SNAPSHOT stills
- Camera filters, archive/restore UI, duplicate dry-run, clearer delete blockers
- Lab wizard: `next_action`, checklist, FACE_PILOT=N/A for CAMERA_LAB; PHYSICAL ≠ `camera_lab_pass`
- VI operator guide + read-only diagnostics PS1 (BOM, no `$home`)

## Owner next steps

See `docs/vi/REALCAM_WINDOWS_OPERATOR.md` and `docs/PR11_REALCAM_ACCEPTANCE_MATRIX.csv`.
