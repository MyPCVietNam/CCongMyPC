# Hướng dẫn Camera / RTSP (PR11-HF)

## Trước khi cập nhật

1. Dừng app.
2. Sao lưu thư mục dữ liệu đang dùng (`-DataDir` / `MYPC_DATA_DIR`) — **không xóa SQLite**.
3. Checkout nhánh hotfix, cài dependency nếu cần, `npm.cmd ci && npm.cmd run build`.
4. Khởi động lại với **cùng** `-DataDir`.

## Sửa camera #12 (hoặc camera hiện có)

1. Mở **Camera** → chọn đúng camera trong danh sách trên cùng.
2. Form tự nạp tên, IP, URI RTSP (không mật khẩu), tài khoản gợi ý.
3. Thấy “Đã lưu credential” → **để trống mật khẩu** nếu không đổi.
4. Sửa IP/đường dẫn nếu cần → **Lưu thay đổi**.
5. **Kiểm RTSP** để xem TCP / 401 / 404 (không tự dò mật khẩu).
6. **Kết nối LIVE** → trạng thái `CONFIG_SAVED` cho đến khi có khung hình giải mã thật.
7. Camera thử nghiệm thừa → **Lưu trữ** (giữ lịch sử). Chỉ xóa cứng khi không còn dữ liệu lịch sử.

## Lưu ý

- TCP 554 mở **không** phải CAMERA_LAB PASS.
- Không nhúng mật khẩu vào URI RTSP.
- Đường dẫn gợi ý thủ công: `/ch1/main`, `/h264/ch1/main/av_stream`, `/Streaming/Channels/101` — xác nhận theo firmware.
