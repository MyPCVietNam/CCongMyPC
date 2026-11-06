# P02-USB-HF2 — Runbook chủ sở hữu (verified binding + candidate thật)

**Cổng:** `127.0.0.1:18878` · DataDir mới · **KHÔNG** đụng 18876/18877.

## Root cause (HF1 → HF2)

1. `enrich_for_capture` / `_link_wmi_to_dshow` từng đánh dấu `mapping_verified=True` chỉ vì có tên PnP — **đã gỡ**.
2. Mở `cv2.VideoCapture("video=Name", CAP_DSHOW)` là cú pháp FFmpeg, không phải OpenCV DSHOW — **đã cấm**; chỉ mở bằng **index DirectShow đã liên kết**.
3. Index cũ không bị xóa khi mất mapping — **đã clear** trước khi re-resolve.
4. Script HF1 `-Mode Start` không chạy backend — dùng **`p02_usb_hf2_candidate_18878.ps1`** (Start thật + health).

## Script ứng viên

```powershell
.\scripts\windows\p02_usb_hf2_candidate_18878.ps1 -Mode Prepare -FullSourceZip <FULL.zip> -ExpectedSha256 <hex> [-ModelsSourceDir <onnx>]
.\scripts\windows\p02_usb_hf2_candidate_18878.ps1 -Mode Preflight
.\scripts\windows\p02_usb_hf2_candidate_18878.ps1 -Mode Start
.\scripts\windows\p02_usb_hf2_candidate_18878.ps1 -Mode Export
```

Prepare tạo venv Python 3.12, cài `requirements.txt` + `requirements-windows.txt` (pywin32/WMI), giải nén FULL ZIP đã PIN SHA256, đặt weights vào `models\weights` và set `MYPC_MODELS_DIR`.

## Kiểm tra vật lý (vẫn BLOCKED cho đến khi owner chạy)

1. Enumerate — chỉ chọn mục `CAPTURE_MAPPING_VERIFIED=true` / `trusted_live_eligible`.
2. Diagnose — stages: PNP_ID_FOUND → CAPTURE_MAPPING_VERIFIED → OPENED → FRAME_RECEIVED.
3. Actual 1080p MJPG; không tin set(); không kết luận 4K từ tên SP.
4. Rebind cùng device giữ `config_revision`; đổi device → revoke.
5. Unplug/replug / đổi index — không tái dùng index/khung cũ.
6. Hai tab một capture loop; soak 30 phút; CAMERA_LAB USB riêng.

## Gates

| Gate | Status |
|------|--------|
| CODE_FIX | CI |
| USB_WINDOWS_PHYSICAL | BLOCKED |
| USB_STABILITY_30_MIN | BLOCKED |
| USB_CAMERA_LAB_OWNER_SIGN | BLOCKED |
| FACE_PILOT / INSTALLER / PRODUCTION | BLOCKED |

Rollback: quay PR #25 tip `6d1842b` — không đụng DataDir owner.
