# Owner Windows — disposable DataDir smoke/soak (PR16-HF1)

1. Checkout HF1 tip; Python 3.12.x; FastAPI 0.115.14; OpenCV contrib headless 4.13.x; DataDir disposable.
2. LIVE MJPEG vẫn chuyển động — không gọi snapshot. Badge + Camera LIVE health cập nhật ≤5s; ẩn tab thì dừng poll.
3. Bấm Kiểm tra: lane handshake + legacy + LIVE cùng hiển thị; UNKNOWN không ghi đè connection_status khi LIVE đang chạy.
4. Cắt mạng camera ngắn → badge STALE/RECONNECTING (không LIVE giả); khôi phục → FPS UNKNOWN rồi MEASURED (không ~0.3 sau gap).
5. Windows Lab: Tải evidence PHYSICAL sau refresh; đổi camera → wizard reset; ký HMAC → chỉ PASS khi `signed_camera_lab` verified.
6. `python tools/audit_camera_secrets_readonly.py --data-dir <staging> --json` — UNKNOWN ≠ orphan; không xóa.
7. Soak 15–30 phút trước khi tuyên bố ổn định. HEVC A/B vẫn theo checklist PR16.
8. Không merge main; không production DataDir; không đổi firmware/codec tự động.
