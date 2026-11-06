# P02-USB UVC changelog

- Add `LiveUsbUvcGateway` (CAP_DSHOW + optional MSMF) with injectable `open_capture` for CI.
- Stable hashed USB identity (`uvc:sha256…`); never persist OpenCV index as identity.
- Registry lease: one capture loop per USB stable device; multi-viewer share.
- Migration 0013: `source_type`, `usb_stable_id`, friendly name, index hint; binding `usb_stable_id`.
- Trust: material `source_type` / `usb_stable_id` revokes CAMERA_LAB HMAC; RTSP credentials not inherited.
- API: `/usb/enumerate`, `/usb/diagnose`, `/gateway/live/configure-usb`.
- CameraPage: RTSP vs USB selector, enumerate/diagnose, Vietnamese copy, MYPC styling retained.
- Owner runbook + Windows PS1 physical checklist (BOM); gates matrix.
