# Bước owner trên Windows staging (PR16)

1. Checkout tip PR16; Python 3.12.x; FastAPI 0.115.14; DataDir disposable (không production).
2. Xác minh LIVE MJPEG vẫn chạy; header badge cập nhật trong ≤15s sau configure (không kẹt MOCK).
3. Bấm Kiểm tra RTSP: phải thấy HANDSHAKE_ONLY; nếu decoder đang LIVE thì `live_decoder_operational=true`; DB không bị hiểu nhầm là “chưa decode”.
4. Chạy soak 15–30 phút; ghi FPS / reconnect / suspected_corrupt từ diagnostics — stderr HEVC POC vẫn có thể xuất hiện; **không** đồng nhất với `hevc_ref_events` (heuristic).
5. `python tools/audit_camera_secrets_readonly.py --data-dir <staging>` — chỉ đọc; không xóa staged khi còn pending outbox.
6. Windows Lab: promote PHYSICAL nếu chưa; rồi **Ký CAMERA_LAB (HMAC)** với tài khoản PILOT_APPROVE; xác nhận `signed_camera_lab` trên gateway health.
7. A/B HEVC theo `OWNER_HEVC_AB_CHECKLIST_VI.md`.
8. Không đánh FACE_PILOT / INSTALLER / PRODUCTION_READY trong PR16.
