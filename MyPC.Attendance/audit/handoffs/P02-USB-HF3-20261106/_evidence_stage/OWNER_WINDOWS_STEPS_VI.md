# P02-USB-HF3 — Hướng dẫn Windows (candidate đã Prepare + đã Update trước đó)

**KHÔNG** chạy lại Prepare. **KHÔNG** đụng HF5/18876 hay HF1/18877.

1. Tải COMPLETE ZIP (pin + SHA256 trong README sau push freeze).
2. Lấy FULL-SOURCE + SHA256; Update source-only trên HF3 `127.0.0.1:18878`:

```powershell
cd <extract>\MyPC.Attendance\scripts\windows
.\p02_usb_hf3_candidate_18878.ps1 -Mode Stop
.\p02_usb_hf3_candidate_18878.ps1 -Mode Update `
  -FullSourceZip <path\MyPC.Attendance-FULL-SOURCE-P02-USB-HF3.zip> `
  -ExpectedSha256 <hex-lowercase>
.\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
.\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
```

3. Kỳ vọng Diagnose (nếu chưa đạt → BLOCKED + SafeExport):
   - Không còn `coinit:TypeError` / `DSHOW_COINIT_FAILED`
   - `DSHOW_ENUM_OK=true`, `DSHOW_VIDEO_MONIKER_COUNT>=1`
   - `PROPERTY_BAG_BIND_OK_COUNT>=1`, `DEVICE_PATH_READ_OK_COUNT>=1`
   - `VIDEO_DEVICE_PATH_MATCH_COUNT=1`, `CAPTURE_MAPPING_VERIFIED=true`
   - `COM_RELEASE_WARNING_COUNT=0`
4. Chỉ khi mapping PASS: Start → smoke 1080p → soak → CAMERA_LAB **mới**.

Gates vật lý vẫn BLOCKED cho đến khi owner xác nhận.
