# Hướng dẫn lab camera Windows (tiếng Việt)

**Phát triển bởi [MyPC Viet Nam](https://mypc.vn).**

## Mục tiêu

Chứng minh (hoặc bác bỏ trung thực) việc giải mã RTSP/ONVIF từ EZVIZ H8 Pro trên **máy Windows công ty**. TCP mở cổng không đủ để đánh `CAMERA_LAB_PASS`.

## Bước nhanh

1. Clone nhánh `cursor/p015-hf-p02-camera-gateway-83a8`, cài `.venv`, `pip install -r requirements.txt`, build UI (`cd frontend && npm ci && npm run build`).
2. Đặt weights YuNet/SFace vào `models/weights` theo `models/manifest.json` (không commit ONNX lên Git công khai nếu chính sách cấm).
3. Chạy `scripts/windows/Start-MyPCAttendance.ps1` (mặc định `127.0.0.1:8765`).
4. Trong UI: nhập IP/URI RTSP **cục bộ** (không dán mật khẩu vào chat/Git).
5. Gọi API cấu hình gateway LIVE (operator có `CAMERA_MANAGE`) — phản hồi chỉ trả URI đã che mật khẩu.
6. Xem `/api/v1/cameras/gateway/health`: provenance `CAMERA_LIVE`, kích thước native, reconnect.
7. Chạy `scripts/windows/Test-MyPCCamera.ps1 -CameraHost <IP>` và lưu JSON dưới `%ProgramData%\MyPC\Attendance\camera-lab\`.
8. Chỉ khi decode + chất lượng face/body tại vị trí đứng được đo xong mới được đề xuất `CAMERA_LAB_PASS` (review người).

## Cổng kết quả

| Gate | Điều kiện PASS |
|------|----------------|
| CAMERA_LAB | Decode RTSP thật trên Windows + bằng chứng kích thước/FPS/reconnect |
| FACE_PILOT | Sau CAMERA_LAB + đăng ký thật có giám sát |
| WINDOWS_RUNTIME | Ứng dụng chạy ổn định trên Win11 x64 lab |
| INSTALLER | File `.exe` đã biên dịch và kiểm thử — launcher PowerShell **không** đủ |

## Bảo mật

- Không ghi mật khẩu vào log/ZIP/diagnostic.
- Không mở go2rtc/API camera ra LAN mặc định.
- Production: `MYPC_ALLOW_SYNTHETIC_FIXTURES=false`.
