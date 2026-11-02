# PR5 Corrective Findings

Baseline audited code: `d1cb733eeb36a5e10cb14062294895d1f5597bb1`  
Work started from tip `bbbd42c` (docs-only delta). Branch: `cursor/pr5-corrective-p02q-83a8`

| ID | Finding | Root cause | Fix | Test | Status |
|----|---------|------------|-----|------|--------|
| F01 | Predictable session secret default | `secret_key` default literal | Persistent CSPRNG `session.secret`; reject weak in production | `test_pr5_corrective_security` | FIXED |
| F02 | Forged session with historic key | Same signer default | Strong key + forged-session negative test | same | FIXED |
| F03 | AUTO_VALIDATED via JSON flag | `admin_confirm_live_pilot` | 403 UNSIGNED; HMAC `PilotApprovalRecord` | `test_auto_validated_json_flag_rejected` | FIXED |
| F04 | REAL_CAMERA enrollment gap | Always 503; client base64 as live | Signed CAMERA_LAB/staging gate; registry `camera_id` pull | code+existing | FIXED (prod still BLOCKED without approval) |
| F05 | LIVE attendance gap | No verified observe path | `live/observe-shadow` fail-closed; non-authoritative | `test_live_observe_shadow_requires_live` | FIXED (shadow only) |
| F06 | Mutable BGR via setflags | ndarray seal insufficient | Bytes-backed `CameraFrame._pixels` | immutable tests | FIXED |
| F07 | Secret store `except: pass` | configure swallowed errors | Fail closed SECRET_STORE_FAILED | code | FIXED |
| F08 | DNS rebind / ValidationErrorVi swallow | bare `except ValueError` | dns_guard + narrow except | DNS/RTSP unit | FIXED |
| F09 | ready=true for STALE | health treated STALE as ready | `operationally_ready` only OK LIVE | gateway health test | FIXED |
| F10 | Hardcoded AUTO_TEST_ONLY diagnostics | ignored DB settings | Read `CameraQualitySettings` | integration | FIXED |
| F11 | Fake A/B button | enhance-only | `run_paired_recognition` via pipeline | analyze-once | FIXED (synthetic/real when weights) |
| F12 | Report not downloadable | status text only | `?download=true` attachment | report test | FIXED |
| F13 | Alembic silent pass | bare except | record `alembic_error`; raise path available | main.py | FIXED |
| F14 | CAMERA_LAB physical | no company camera | — | — | BLOCKED |
| F15 | FACE_PILOT | no owner pilot | — | — | BLOCKED |
| F16 | Person exit / YOLO | unlicensed | — | — | BLOCKED |
| F17 | Windows installer | not built | — | — | NOT_RUN |
