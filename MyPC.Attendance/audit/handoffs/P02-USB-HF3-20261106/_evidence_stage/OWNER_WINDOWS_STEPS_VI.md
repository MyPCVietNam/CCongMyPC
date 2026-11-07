# P02-USB-HF3 — Hướng dẫn Windows (candidate đã Prepare)

**KHÔNG** Prepare lại. **KHÔNG** đụng 18876/18877.

```powershell
cd <extract>\MyPC.Attendance\scripts\windows
.\p02_usb_hf3_candidate_18878.ps1 -Mode Stop
.\p02_usb_hf3_candidate_18878.ps1 -Mode Update `
  -FullSourceZip <path\MyPC.Attendance-FULL-SOURCE-P02-USB-HF3.zip> `
  -ExpectedSha256 <hex-lowercase>
.\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
.\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
```

Kỳ vọng Diagnose trước khi Start vật lý:
- `DSHOW_ENUM_OK=true`
- `PROPERTY_BAG_BIND_OK_COUNT>=1`, `FRIENDLY_NAME_READ_OK_COUNT>=1`
- `DEVICE_PATH_READ_OK_COUNT>=1`, `DEVICE_PATH_CANONICAL_OK_COUNT>=1`
- đúng 1 cặp PnP↔DevicePath; `CAPTURE_MAPPING_VERIFIED=true`
- `COM_RELEASE_WARNING_COUNT=0`, `MODEL_PINS_PASS=true`

Chỉ khi đạt: Start trên 18878 → smoke 1080p → soak → CAMERA_LAB mới.
Không auto-Start / không ký lab từ synthetic.
