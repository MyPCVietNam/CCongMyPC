# P02-USB-HF2 — Hướng dẫn Windows (chủ sở hữu)

## 1. Tải COMPLETE ZIP (pin commit sau khi đóng gói)

Dùng one-liner trong `README.md` (SHA256 bắt buộc khớp).

## 2. Chuẩn bị ứng viên 18878

```powershell
cd <extract>\MyPC.Attendance\scripts\windows
.\p02_usb_hf2_candidate_18878.ps1 -Mode Prepare `
  -FullSourceZip <path\to\MyPC.Attendance-FULL-SOURCE-P02-USB-HF2.zip> `
  -ExpectedSha256 <hex-from-SHA256SUMS> `
  -ModelsSourceDir <thư-mục-onnx-đã-xác-minh>
.\p02_usb_hf2_candidate_18878.ps1 -Mode Preflight
.\p02_usb_hf2_candidate_18878.ps1 -Mode Start
# Kiểm tra: Invoke-WebRequest http://127.0.0.1:18878/api/v1/health
.\p02_usb_hf2_candidate_18878.ps1 -Mode Export
```

- Cổng **chỉ** `18878`. Không dừng/đụng 18876/18877.
- Không copy DataDir/HMAC/SQLite từ HF5 hoặc P02-HF1.
- `MYPC_MODELS_DIR` trỏ tới weights đã PIN SHA256 (`models/manifest.json`).

## 3. Kiểm tra binding USB

1. UI Camera → Liệt kê USB → chỉ chọn mục `trusted_live_eligible` / `CAPTURE_MAPPING_VERIFIED`.
2. Diagnose: đủ 4 stage; frame thật; không tin `set()`; không kết luận 4K từ tên SP.
3. Configure LIVE → xác nhận MJPEG; hai tab một loop.
4. Rút/cắm lại USB: index có thể đổi; phải map lại; không tái dùng index cũ.
5. Đổi thiết bị khác → `config_revision` rotate / HMAC revoke.

## 4. Gates vẫn BLOCKED

USB_WINDOWS_PHYSICAL, soak 30 phút, CAMERA_LAB USB ký, FACE_PILOT, installer, production — chỉ PASS khi có bằng chứng owner.
