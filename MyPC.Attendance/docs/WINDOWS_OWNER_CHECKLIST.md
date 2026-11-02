# MyPC Attendance - owner Windows camera lab checklist

Device: company-authorized Windows 10/11 machine on the same LAN as EZVIZ H8 Pro 3K. Camera firmware/RTSP/ONVIF behavior must be physically measured, not assumed from device specifications.

1. Checkout exact reviewed app build; preserve SHA and clean status; verify Python 3.12 x64, Node, dependencies and OpenCV models/licensing. Do not run a Cloud mock script on Windows as proof of camera functionality.
2. Start backend bound to `127.0.0.1` and open authenticated local browser. Protect camera secret in application local secure store, never on command line or in screenshots.
3. Use local IPv4 camera endpoint in UI and check main/substream selection. Do not expose RTSP 554 or Web app through port forwarding/tunnels to Internet.
4. Confirm actual camera LIVE decoded frames: frame provenance CAMERA_LIVE, consistent camera ID/config generation, decoded width/height, measured FPS, fresh monotonic timestamps and codec. Compare main/sub. Socket TCP connectivity alone does not pass.
5. Check exposure/blur native face width and eye distance with authorized employee standing on marked position at first-floor doorway, no hat. Compare morning daylight and night IR; report insufficient optics/mounting honestly.
6. Run authorized supervised enrollment from the same selected camera. Verify one-person frames, front/left/right face, motion/body evidence only if camera view captures enough; no false completion on partial body.
7. Run labeled known and unknown tests from authorized dataset; count correct, misses, wrong person and unknown false acceptance. Compare original/enhanced with same exact source frame/model/gallery/threshold; do not auto-enable enhancement without independent approval.
8. Disconnect/reconnect camera, simulate wrong password/path, change config, restart Windows and app; ensure evidence and approvals fail closed on stale data and no phantom attendance.
9. Verify AM 08:15-08:45, PM 17:00-23:55:59.999, zero late grace at 08:30, only one AM/PM record, overtime only verified exit. Do not modify historical attendance.
10. Human signs a sanitized lab manifest with run_id, commit, time zone, camera_id, config generation, official measured dimensions, FPS, source proof, sample counts and BLOCKED reasons; no face photos, templates, employee names, RTSP passwords or `.env` exported.
11. Do not promote CAMERA_LAB/FACE_PILOT from a user-provided count or a checkbox alone. Require fresh server run measurements, owner review and signed evidence.
12. Keep installer blocked until a real signed/unsigned test installer has been installed, started, updated and uninstalled with data retention verified on Windows.

Signed by owner: __________________  Run ID: _______________  Date/time (UTC+07): _______________  Final gate: BLOCKED / PASS / FAIL
