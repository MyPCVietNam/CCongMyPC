# P02-USB-HF3 — Runbook chủ sở hữu (DirectShow COM + DevicePath)

**Cổng:** `127.0.0.1:18878` · DataDir **mới** `p02-usb-hf3-candidate` · **KHÔNG** đụng 18876/18877 / HF2 DataDir.

## Root cause đã sửa

**Identity patch (PR #27):** khớp DevicePath↔PnP chỉ khi bằng nhau tuyệt đối VID+PID+MI+toàn bộ instance token — không dùng substring / bỏ qua MI.

## Root cause đã sửa

`Dispatch('SystemDeviceEnum')` → `CO_E_CLASSSTRING` (0x800401F3).  
Đúng: `CoCreateInstance(CLSID_SystemDeviceEnum, IID_ICreateDevEnum)` rồi
`CreateClassEnumerator(CLSID_VideoInputDeviceCategory)` và đọc **DevicePath**.

## Ứng viên HF3

```powershell
cd <extract>\MyPC.Attendance\scripts\windows
.\p02_usb_hf3_candidate_18878.ps1 -Mode Prepare `
  -FullSourceZip <FULL.zip> -ExpectedSha256 <hex> `
  -ModelsSourceDir <thư-mục-onnx-đã-PIN>
.\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
.\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
.\p02_usb_hf3_candidate_18878.ps1 -Mode Start
.\p02_usb_hf3_candidate_18878.ps1 -Mode SafeExport
.\p02_usb_hf3_candidate_18878.ps1 -Mode Stop
```

Diagnose (không cần admin) in redacted: `PNP_VIDEO_COUNT`, `DSHOW_VIDEO_MONIKER_COUNT`,
`VIDEO_DEVICE_PATH_MATCH_COUNT`, `CAPTURE_MAPPING_VERIFIED`, `VERIFIED_INDEX`,
`MODEL_PINS_PASS`, blocker code. Không in raw PnP / DevicePath / frame.

## Smoke vật lý (sau khi Diagnose PASS)

1. Enumerate → chỉ chọn `trusted_live_eligible` / CAPTURE_MAPPING_VERIFIED.
2. Capture thật 1920x1080; index ephemeral; không kết luận 4K từ tên SP.
3. Unplug/replug → index có thể đổi; cùng DevicePath/PnP; không tái dùng index cũ.
4. Hai tab / một capture loop.
5. Soak 30 phút.
6. **Chỉ sau đó** ký CAMERA_LAB USB mới — không tái dùng HMAC EZVIZ.

## Gates

| Gate | Status |
|------|--------|
| CODE_FIX (0x800401F3 ProgID) | CI |
| USB_WINDOWS_PHYSICAL | BLOCKED đến owner PASS |
| USB_STABILITY_30_MIN | BLOCKED |
| USB_CAMERA_LAB_OWNER_SIGN | BLOCKED |
| FACE_PILOT / INSTALLER / PRODUCTION | BLOCKED |

Rollback: PR #26 tip `146d04c`. Không đụng DataDir owner.
