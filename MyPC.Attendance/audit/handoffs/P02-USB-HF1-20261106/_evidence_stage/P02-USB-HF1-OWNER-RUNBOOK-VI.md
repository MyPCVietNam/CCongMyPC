# P02-USB-HF1 — Runbook chủ sở hữu (ổn định PnP↔DirectShow + rebind)

**Cổng ứng viên:** `127.0.0.1:18878` · DataDir mới · **KHÔNG** đụng 18876/18877.

## Script an toàn

`scripts/windows/p02_usb_hf1_candidate_18878.ps1` — chế độ `Prepare` / `Preflight` / `Start` / `Export`.
Verify FULL-SOURCE ZIP bằng SHA256 trước khi giải nén. Chỉ copy file `.onnx` đã PIN_MATCH nếu cần — không copy SQLite/secret/HMAC/ảnh.

## Thứ tự kiểm tra vật lý (BLOCKED cho đến khi owner chạy)

1. Liệt kê USB — chọn UGREEN có `trusted_live_eligible=true` / `mapping_verified`.
2. Đo chế độ — actual WxH/FOURCC (ưu tiên MJPG 1920×1080); không tin `set()`.
3. Gắn USB LIVE → CONFIG_SAVED; rebind cùng thiết bị **giữ** `config_revision`.
4. Rút/cắm — cùng stable_id (index có thể đổi); thiết bị khác → thu hồi trust.
5. Hai tab MJPEG — một capture loop.
6. Overlay AI — face ≥120 px (ưu tiên ≥160) tại vị trí chấm công.
7. Restart backend + DataDir ứng viên — rebind cùng identity, không xoay revision nếu không material.
8. Soak 30 phút — ghi FPS/CPU.
9. CAMERA_LAB USB riêng — không thừa kế EZVIZ HMAC. Không dán secret vào chat.

## Cổng (gates)

| Gate | Status |
|------|--------|
| CODE_FIX | CI |
| USB_WINDOWS_PHYSICAL | BLOCKED |
| USB_STABILITY_30_MIN | BLOCKED |
| USB_CAMERA_LAB_OWNER_SIGN | BLOCKED |
| FACE_PILOT / INSTALLER / PRODUCTION_READY | BLOCKED |
