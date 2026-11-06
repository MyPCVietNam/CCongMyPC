# P02-USB-HF3 — Hướng dẫn Windows (candidate đã Prepare)

**KHÔNG** chạy lại Prepare. **KHÔNG** đụng HF5/18876 hay HF1/18877 DataDir/HMAC.

1. Tải COMPLETE ZIP (pin + SHA256 trong README sau khi agent push freeze).
2. Giải nén FULL-SOURCE; lấy SHA256 của `MyPC.Attendance-FULL-SOURCE-P02-USB-HF3.zip`.
3. Update source-only rồi Diagnose trên HF3 `127.0.0.1:18878`:

```powershell
cd <extract>\MyPC.Attendance\scripts\windows
# Dừng ứng viên nếu đang chạy (Update từ chối cổng lạ; chỉ stop PID uvicorn đã xác minh):
.\p02_usb_hf3_candidate_18878.ps1 -Mode Stop
.\p02_usb_hf3_candidate_18878.ps1 -Mode Update `
  -FullSourceZip <path\MyPC.Attendance-FULL-SOURCE-P02-USB-HF3.zip> `
  -ExpectedSha256 <hex-lowercase>
.\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
.\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
```

4. Kỳ vọng Diagnose (chưa có thì vẫn BLOCKED, gửi SafeExport):
   - `PNP_VIDEO_COUNT=1`
   - `PROPERTY_BAG_BIND_OK_COUNT>=1`, `FRIENDLY_NAME_READ_OK_COUNT>=1`
   - `DEVICE_PATH_READ_OK_COUNT>=1`, `DEVICE_PATH_CANONICAL_OK_COUNT>=1`
   - `VIDEO_DEVICE_PATH_MATCH_COUNT=1`, `CAPTURE_MAPPING_VERIFIED=true`
   - `COM_RELEASE_WARNING_COUNT=0`
5. Chỉ khi mapping PASS:

```powershell
.\p02_usb_hf3_candidate_18878.ps1 -Mode Start
Invoke-WebRequest http://127.0.0.1:18878/api/v1/health
.\p02_usb_hf3_candidate_18878.ps1 -Mode SafeExport
```

6. Smoke vật lý sau đó: 1080p → unplug/replug → dual tab → soak 30′ → USB CAMERA_LAB **mới**.

Gates vật lý vẫn BLOCKED cho đến khi owner xác nhận.
