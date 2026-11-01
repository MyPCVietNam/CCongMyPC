# Phòng thí nghiệm Camera Windows — MyPC Attendance

## Mục tiêu

Kiểm tra camera EZVIZ H8 Pro (CS-H8-R100-1J5WKFL, firmware V5.3.8 build 240329) trên máy Windows 10/11 x64 **mà không** đưa mật khẩu vào Git hay tham số dòng lệnh.

**Lưu ý:** Camera nằm trong danh sách ONVIF của hãng **không** đồng nghĩa RTSP đã phát được trên máy bạn.

## Chuẩn bị

1. Cài Python 3.12, tạo `.venv`, `pip install -r backend/requirements.txt`.
2. (Tuỳ chọn) `npm install && npm run build` trong `frontend/`.
3. Chạy `scripts/windows/Start-MyPCAttendance.ps1` (mặc định production, loopback).
4. Đăng nhập, **đổi mật khẩu** nếu có tệp `FIRST_RUN_ADMIN.txt`, rồi xóa tệp đó.

## Kiểm tra camera (thứ tự bắt buộc)

1. Chạy `Test-MyPCCamera.ps1 -CameraHost <IP_LAN>` — ghi TCP ONVIF/RTSP.
2. Trong UI **Camera & Vùng nhận diện**: thêm camera, nhập credential cục bộ, bấm **Kiểm tra kết nối**.
3. Chỉ khi có khung hình **CAMERA THẬT (LIVE)** mới cân nhắc `CAMERA_LAB_PASS`.
4. Lỗi LIVE sẽ trả `LIVE_NOT_IMPLEMENTED` / `CAMERA_UNAVAILABLE` — **không** tự thay bằng ảnh mô phỏng.
5. Vẽ ROI nhận diện; ROI ra về tách riêng và phải hiệu chỉnh lại khi đổi góc máy.

## Đăng ký khuôn mặt

- Chỉ nhân viên tham gia, có xác nhận thông báo sinh trắc học.
- Trên CI/Linux dùng nguồn DEMO/fixture; **REAL_CAMERA** bị chặn đến khi lab thật đạt.
- Có phương án chấm công không sinh trắc học (PIN/timekeeper — mở rộng P02+).

## Cổng trạng thái

| Cổng | Ý nghĩa |
|------|---------|
| WINDOWS_RUNTIME | Script chạy được trên Windows host |
| CAMERA_LAB | Đã giải mã khung hình LIVE thật |
| FACE_PILOT | Pilot khuôn mặt có kiểm soát tại cửa hàng |
| EXIT_VERIFICATION | Theo dõi hướng ra về — hiện BLOCKED |

## Bảo mật

- Không commit `data/`, `secrets/`, ảnh khuôn mặt, embedding, mật khẩu.
- go2rtc chỉ bind `127.0.0.1` (xem `gateway/go2rtc.yaml.template`).
