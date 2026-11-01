# Hướng dẫn vận hành nhanh (P00-HF + P01)

1. **Khởi động local:** `scripts/windows/Start-MyPCAttendance.ps1` (hoặc uvicorn trên Linux/dev).
2. **Đăng nhập** → đổi mật khẩu nếu hệ thống yêu cầu → xóa `FIRST_RUN_ADMIN.txt`.
3. **Camera:** nhập IP LAN + credential trong UI; bấm Kiểm tra kết nối. Nếu không có LIVE frame, hệ thống báo lỗi rõ — không tự dùng ảnh mô phỏng.
4. **ROI:** kéo/nhập tọa độ chuẩn hóa; lưu lại (cần quyền quản lý camera).
5. **Đăng ký khuôn mặt:** chọn nhân viên → xác nhận thông báo sinh trắc → thu mẫu DEMO trước khi CAMERA_LAB đạt.
6. **Chấm công:** cửa sổ chiều 17:00–23:55; mốc chọn mẫu 18:00; không bịa timestamp.
7. **Xuất chẩn đoán:** `Export-MyPCAttendanceDiagnostics.ps1` (không gồm mật khẩu/template).

Lỗi thường gặp:

- `LIVE_NOT_IMPLEMENTED` — chưa giải mã RTSP thật.
- `CAMERA_LAB_BLOCKED` — chưa mở đăng ký từ camera thật.
- `403 DEMO` — môi trường production tắt mock observation.
