# Hướng dẫn chủ sở hữu — lab camera Windows (P02Q / PR5)

1. Chạy backend trên PC công ty (LAN), đăng nhập ADMIN.
2. Thêm camera: URI RTSP **không** kèm mật khẩu; nhập tài khoản/mật khẩu riêng trong form.
3. **Gắn nguồn LIVE** → kiểm `GET /api/v1/cameras/gateway/health` (`provenance=CAMERA_LIVE`, `operationally_ready`, DECODED_MEASURED).
4. TCP PASS ≠ decode PASS. Ghi width×height thật, FPS đo, tuổi khung, DAY/DUSK/IR.
5. Chạy `scripts/windows/Test-MyPCCamera.ps1 -CameraHost <IP>` — giữ `camera_lab_pass=false` đến khi ký tay.
6. Phê duyệt CAMERA_LAB / FACE_PILOT chỉ qua API phê duyệt đã ký (`PILOT_APPROVE`), không cờ JSON.
7. AUTO_VALIDATED chỉ sau pilot A/B thật + chữ ký server.
