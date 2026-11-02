# Hướng dẫn kiểm tra camera Windows (chủ sở hữu) — PR7

**Lưu ý:** Cloud Agent Linux **không** truy cập được LAN camera công ty. Không đánh **PASS** CAMERA_LAB / FACE_PILOT / EXIT / INSTALLER khi chưa có bằng chứng vật lý trên máy Windows.

## Chuẩn bị

1. Checkout đúng nhánh ứng dụng (không dùng `main` chỉ LICENSE, không dùng P00 46 tests).
2. Cài Python 3.12 + Node, tạo venv, cài dependency, `npm run build`.
3. Đặt file ONNX đúng SHA trong `models/weights` (xem `docs/MODEL_PROVISIONING.md`).
4. Chạy backend chỉ `127.0.0.1` — không mở tunnel công khai, không đưa mật khẩu RTSP lên argv.

## Các bước camera (IPv4 LAN)

1. Đăng nhập UI localhost bằng tài khoản quản trị.
2. Thêm camera, bật nguồn LIVE, nhập **IPv4 LAN literal** (không hostname) + credential trong form UI (không `-Password` trên dòng lệnh).
3. Gọi `/api/v1/cameras/gateway/health` và preview: ghi **DECODED_MEASURED** width×height, FPS đo được, tuổi khung, provenance=`CAMERA_LIVE`.
4. TCP mở cổng 554 **không** đủ → vẫn BLOCKED cho CAMERA_LAB.
5. Kiểm DAY và NIGHT_IR; đo face width / inter-eye trên pixel gốc (≥120px khi đủ điều kiện lab).
6. Ghi bằng chứng qua `POST .../evidence/record` với kích thước **khớp** khung server đo được; chỉ khi đủ mới `PHYSICAL_VERIFIED`.
7. FACE_PILOT: mẫu labeled known + unknown (không upload ảnh nhân viên lên GitHub).
8. Chạy `scripts/windows/Test-MyPCCamera.ps1 -CameraHost <IPv4>` — script vẫn giữ các bước decode/face là BLOCKED cho đến khi bạn có bằng chứng thật.

## Kết quả mong đợi trong báo cáo

- `camera_lab_pass=false` cho đến khi có phê duyệt HMAC gắn `evidence_id` PHYSICAL_VERIFIED.
- Cờ cấu hình `settings_flag_camera_lab` **không** đồng nghĩa đã PASS vật lý.
- INSTALLER giữ BLOCKED trừ khi cài/gỡ thật trên Windows thành công.
