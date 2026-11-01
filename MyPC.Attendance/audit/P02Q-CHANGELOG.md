# P02Q Changelog (P02-HF + P02Q)

## Added

- `vision/camera/registry.py` — per-camera source registry
- `vision/camera/rtsp_policy.py` — strict LIVE URI policy
- `vision/camera/native_frame.py` — NativeDecodedFrame contract
- `vision/camera/ffprobe_allowlist.py` — sanitized metadata
- `vision/faces/native_geometry.py` — YuNet inverse map + native gate
- `vision/faces/adaptive_quality.py` — shadow enhance + mode machine
- `vision/faces/paired_ab.py` — paired A/B aggregate evaluator
- Alembic `20261102_0004` — stream profiles, quality settings, A/B runs
- Quality APIs: diagnostics, analyze-once, settings GET/PUT, evaluation/run, redacted report
- Vietnamese Camera quality UI controls
- Unit/integration tests `test_p02q_*`
- Audit package P02Q-*

## Changed

- `LiveRTSPGateway` — immutable frames, measured FPS, overwritten_latest, idempotent start, invalidate
- `GET /cameras/{id}/preview` — registry-backed; fail-closed for unbound LIVE
- `POST /gateway/live/configure` — strict policy + bind-before-start
- `validate_rtsp_url` / `redact_url` — aligned with REDACTED policy
- App shutdown stops camera gateways
- Windows `Test-MyPCCamera.ps1` P02Q readiness steps

## Not claimed

- Physical 2880×1620 LIVE decode
- AUTO_VALIDATED promotion
- CAMERA_LAB / FACE_PILOT / installer PASS
- Merge to `main`
