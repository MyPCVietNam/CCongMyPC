# P02 Camera Gateway Report

## Implemented

- `CameraGateway` ABC with `MockFrameGateway`, `AuthorizedRecordedVideoGateway`, `LiveRTSPGateway`
- Distinct `StreamProvenance`: `CAMERA_LIVE` / `AUTHORIZED_RECORDED` / `MOCK`
- `CameraFrame` immutable metadata: ids, native size, capture/receive UTC, decoder status
- Live gateway: single OpenCV/FFmpeg capture thread, latest-frame overwrite (drop stale), reconnect backoff, `sanitize_rtsp_for_log`
- API: `GET /api/v1/cameras/gateway/health`, `POST /api/v1/cameras/gateway/live/configure` (URI never echoed with password)
- `camera_lab_pass` hard-coded **false** in gateway health responses

## Not claimed

- No EZVIZ RTSP decode on Windows in this agent run → **CAMERA_LAB=BLOCKED**
- No FACE_PILOT, INSTALLER, or EXIT_VERIFICATION PASS
- go2rtc not enabled by default
