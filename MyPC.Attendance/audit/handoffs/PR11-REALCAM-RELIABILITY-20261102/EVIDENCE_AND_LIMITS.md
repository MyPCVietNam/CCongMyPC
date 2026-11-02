# Evidence, code links and limits

## Confirmed from owner-provided images/logs
- Windows 10 application running on localhost with preserved DataDir; administrator authenticated. Secrets ACL had previously been repaired and application now runs.
- Real H8 Pro 3K live preview at measured 2880x1620, approximately 20.4-21.4 FPS, provenance CAMERA_LIVE.
- Intermittent partial image corruption/blank regions reported and displayed.
- Python/OpenCV logs: `hevc: Could not find ref with POC 55`, `POC 29`, `POC 8`, `POC 4`, `POC 90`; `cu_qp_delta -60/-112 outside valid range [-26,25]`. No full duration/error rate available.
- Camera selector shows IDs #1 through #12, including #2/#3 configured MOCK, and #1 actively LIVE. The user says deleting profiles does not work; no specific HTTP DELETE response was provided.
- Mock profile #3 displayed `Internal Server Error`. The exact failing API endpoint and traceback are unknown.
- Camera status signals are inconsistent between UI surfaces (`MOCK`, `NOT_CONFIGURED`, `CONFIG_SAVED`, LIVE preview). Physical image may be real even when overall CAMERA_LAB remains blocked.
- Windows Lab screenshot includes a lab run with `state=OWNER_REVIEWED`, `LIVE_SOURCE_MEASURED=true`, `PHYSICAL_CONNECTIVITY_REVIEWED=true`, `camera_lab_pass=false`, `face_pilot_pass=false`, and evidence class `PHYSICAL_VERIFIED`, while buttons report missing LIVE_MEASURED prerequisite. The actual server transition cause has not been independently reproduced.
- Dependency install was successful, frontend Vite build successful, npm audit reported four advisories (3 moderate, 1 high).

## Confirmed from targeted public source inspection
- `frontend/src/pages/CameraPage.tsx` uses a preview HTTP request every 1500 ms, changing to 8000 ms after at least 3 errors, and displays a base64 data URI image. This implies <1 FPS UI image refresh despite >20 FPS decoder telemetry. The source may change in future commits; re-audit exact checked-out HEAD.
- CameraPage defines `deleteCam`, `archiveCam`, `configureLive`, `stopLive`, `testRtsp` and `loadQuality`, with API routes that must be audited for real behavior and error handling. UI deletion is NOT proof that hard delete must be permitted on a referenced camera.
- React camera selection reloads safe fields (`username_hint`, `rtsp_uri_safe`), intentionally blanks password and supports explicit credential replace.
- Public repository directory inventory confirms relevant code in `backend/app/vision/camera`, `backend/app/api/cameras.py`, `backend/app/services/lab_run_service.py`, `frontend/src/pages/CameraPage.tsx`, and related files.

Code references:
- https://github.com/MyPCVietNam/CCongMyPC/blob/729fb6acd69cd4dcd328cc919260a1931efef11d/MyPC.Attendance/frontend/src/pages/CameraPage.tsx
- https://github.com/MyPCVietNam/CCongMyPC/tree/cursor/pr11-secret-acl-hf-83a8/MyPC.Attendance/backend/app/vision/camera
- https://github.com/MyPCVietNam/CCongMyPC/blob/729fb6acd69cd4dcd328cc919260a1931efef11d/MyPC.Attendance/backend/app/api/cameras.py
- https://github.com/MyPCVietNam/CCongMyPC/blob/729fb6acd69cd4dcd328cc919260a1931efef11d/MyPC.Attendance/backend/app/services/lab_run_service.py

## Independent external technical references
- Official EZVIZ H8 Pro 3K specifications: H.265/H.264, dual-stream, 2880x1620 max, Ethernet and 2.4GHz Wi-Fi. https://www.ezviz.com/inter/product/h8-pro-3k/43242
- FFmpeg RTSP demuxer supports RTP-over-TCP and UDP, socket I/O timeout/reordering options. https://ffmpeg.org/ffmpeg-protocols.html#rtsp
- Frigate troubleshooting: decoder errors near startup versus persistent damaged bitstream, and packet sequencing. https://docs.frigate.video/troubleshooting/common_errors/

## Important honesty boundary
This package is a source-informed audit and implementation mandate, NOT a copy of the complete source tree and NOT a claim of full source runtime verification. A complete file-by-file audit and tests must be performed by Cursor with a checkout of the pinned repository and an owner Windows test run. No full private source ZIP, RTSP credentials, sample raw face images or SQLite data were supplied to this package.
