# P02-USB-HF2 acceptance matrix

| ID | Criterion | Result |
|----|-----------|--------|
| A1 | PnP exists, DShow correlation absent → unverified; cannot trusted LIVE | CI PASS |
| A2 | Duplicate friendly names / distinct PnP → fail closed | CI PASS |
| A3 | Verified unique mapping opens correct index; index may change after replug | CI PASS (unit) — physical BLOCKED |
| A4 | Index-only candidate → HTTP 409 untrusted | CI PASS |
| A5 | Identity lost mid-stream → no stale index/frame; not CAMERA_LAB ready | CI PASS |
| A6 | Same USB config/reconnect keeps revision; different device revokes | CI PASS |
| A7 | Parallel tabs one capture loop / reconnect contract | CI PASS (existing) |
| A8 | PS1 Prepare/Preflight/Start/Export contract + health | Script contract CI PASS; Windows physical Start **BLOCKED** |
| A9 | MJPEG/RTSP + FACE_PILOT/attendance gates unchanged | CI PASS (no policy widen) |
| G-PHYS | USB_WINDOWS_PHYSICAL | **BLOCKED** |
| G-SOAK | USB_STABILITY_30_MIN | **BLOCKED** |
| G-LAB | USB_CAMERA_LAB_OWNER_SIGN | **BLOCKED** |
| G-FP | FACE_PILOT / INSTALLER / PRODUCTION | **BLOCKED** |
