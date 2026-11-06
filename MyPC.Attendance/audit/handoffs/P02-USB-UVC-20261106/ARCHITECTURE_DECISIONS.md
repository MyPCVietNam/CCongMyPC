# Architecture decisions — P02-USB

1. **Provenance:** USB frames use `StreamProvenance.CAMERA_LIVE` with `source_type=USB_UVC` extras — physical USB is LIVE, never MOCK/REPLAY.
2. **Identity:** Persist hashed PnP/`uvc:` stable_id only; index is ephemeral hint. Ambiguous OpenCV-only enum is fail-closed unless owner allow_ambiguous.
3. **Trust isolation:** Switching RTSP↔USB or changing usb_stable_id rotates config_revision and revokes prior PHYSICAL/HMAC. EZVIZ CAMERA_LAB does not transfer.
4. **Lease:** One decode/capture loop per `usb:` stream fingerprint; browser viewers subscribe via registry.
5. **Honesty:** Report measured WxH/FOURCC/FPS after read(); product name “4K” ≠ verified 4K capture.
6. **Safety:** No attendance/FACE_PILOT side-effects from USB connect or overlay preview.
