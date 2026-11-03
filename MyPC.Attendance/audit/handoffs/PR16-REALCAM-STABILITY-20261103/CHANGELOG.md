# PR16 CHANGELOG — RealCam stability, HEVC diagnostics, gate honesty

## CODE_FIX

- Gateway: corrupt-frame hot-loop sleep; reconnect lifetime/success/recovery telemetry; `get_latest_frame` respects RECONNECTING; `native_decoder_error_category=UNAVAILABLE`; clarify `hevc_ref_events` = image-stat only; CAP_PROP_BUFFERSIZE set result recorded.
- `test_rtsp`: handshake-only persistence; do not clobber DB status with CONFIG_SAVED on probe OK; return `handshake_only` + `live_decoder_operational`.
- Diagnostics: OpenCV runtime probe on `/api/v1/system/diagnostics`.
- Frontend: runtime-badge poll (15s, visibility-aware); CameraPage decoder-first UI state; RTSP diag shows HANDSHAKE_ONLY lane.
- Windows Lab: HMAC sign step after PHYSICAL_VERIFIED (PILOT_APPROVE); no checkbox bypass.
- Tools: `audit_camera_secrets_readonly.py` (counts/paths only).
- Verify script: SHA256 required ZIPs = hard fail; extras = WARNING only.

## NOT DONE / BLOCKED

- Native FFmpeg stderr capture per camera.
- LIVE_STABILITY_PASS / CAMERA_LAB_SIGNED / FACE_PILOT on this cloud agent.
- Credential rotate / Git history rewrite.
- Auto-delete staged secrets.
