# P02-USB UVC — Runbook chủ sở hữu (Windows 10)

**Cổng ứng viên cô lập:** `127.0.0.1:18878`  
**KHÔNG** đụng `18876` (HF5 EZVIZ) hay `18877` (P02-HF1), DataDir/SQLite/HMAC của chúng.

## Trạng thái cổng (gates)

| Gate | Trạng thái |
|------|------------|
| CODE_FIX (CI / fake-device) | Xem báo cáo PR |
| USB_WINDOWS_PHYSICAL | **BLOCKED** — chỉ owner chạy |
| USB_STABILITY_30_MIN | **BLOCKED** |
| USB_CAMERA_LAB_OWNER_SIGN | **BLOCKED** |
| FACE_PILOT | **BLOCKED** |
| INSTALLER / PRODUCTION_READY | **BLOCKED** |

Không dán challenge/cookie/HMAC/mật khẩu admin vào chat hay console log.

## Chuẩn bị DataDir mới

1. Tạo thư mục trống riêng, ví dụ `%LOCALAPPDATA%\MyPC.Attendance\p02-usb-candidate\`.
2. Dùng venv Python 3.12 hiện có của P02-HF1 (không ghi đè HF5).
3. Khởi động backend ứng viên trên **18878** với `DATA_DIR` trỏ tới thư mục mới + admin bootstrap cục bộ.
4. Mở `http://127.0.0.1:18878` — footer vẫn `Phát triển bởi MyPC Việt Nam` → https://mypc.vn.

## Thứ tự kiểm tra vật lý (owner)

1. **Liệt kê USB** — Trang Camera → loại nguồn `USB (Windows UVC)` → *Liệt kê USB*. Chọn tường minh **UGREEN Camera 4K** (không chọn mục “ambiguous / chỉ số OpenCV”).
2. **Đo chế độ** — *Đo chế độ capture*. Ghi `actual_width`×`actual_height` và FOURCC sau `read()` (không tin `cap.set()`). Mục tiêu ưu tiên: MJPG **1920×1080**. 720p là fallback. **Không** kết luận 4K chỉ vì tên sản phẩm.
3. **Gắn USB LIVE** — *Gắn USB LIVE*. Trạng thái kỳ vọng: `CONFIG_SAVED` → decoder `USB_CONNECTED` khi có khung; transport browser vẫn **UNVERIFIED** đến khi heartbeat client được chứng minh.
4. **Hai viewer** — mở hai tab MJPEG cùng camera; chỉ **một** capture loop (registry lease).
5. **Overlay AI** — bật overlay YuNet; ngưỡng ≥120 px (ưu tiên ≥160). Preview **không** ghi attendance / không FACE_PILOT PASS.
6. **Rút/cắm lại** — rút USB: LIVE/biometric fail nhanh, không khung giả. Cắm lại: phải khớp **cùng** `stable_id` hashed; nếu index đổi nhưng PnP khớp → OK; nếu thiết bị khác → fail-closed.
7. **Đổi thứ tự index** — nếu có nhiều webcam, xác nhận không tự nhảy sang camera khác.
8. **Restart backend** — rebind cùng stable_id + config_revision; không auto-start mọi thiết bị enumerate.
9. **Soak 30 phút** — ghi FPS/CPU; cổng `USB_STABILITY_30_MIN` chỉ PASS khi owner hoàn tất.
10. **CAMERA_LAB USB** — lab FSM trên khung USB thật; ký HMAC riêng (không thừa kế EZVIZ). Không paste secret vào chat.

## Script Windows (owner)

Xem `scripts/windows/p02_usb_uvc_physical_checks.ps1` — chạy local, ghi evidence redacted vào thư mục ứng viên.

## Cách ly

- Port **18878** + DataDir mới only.
- Giữ HF5 `18876` và P02-HF1 `18877` nguyên trạng.
- Không copy SQLite/secret/HMAC giữa các DataDir.
