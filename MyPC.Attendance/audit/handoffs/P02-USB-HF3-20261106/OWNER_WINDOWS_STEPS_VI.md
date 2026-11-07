# P02-USB-HF3 — Owner Windows (PID safety V3)

**KHÔNG** Prepare. **KHÔNG** đụng 18876/18877 / DataDir / venv / model / HMAC.  
**KHÔNG** Start / Stop / runtime harness cho đến khi audit độc lập xác nhận bản V3 này.

V2 COMPLETE (`58017ee3…`) có harness runtime **không an toàn** — không chạy trên máy owner.

```powershell
cd <extract>\MyPC.Attendance\scripts\windows
.\p02_usb_hf3_candidate_18878.ps1 -Mode Update `
  -FullSourceZip <FULL.zip> -ExpectedSha256 <hex>
.\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
.\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
# Sau audit V3 mới chạy (mặc định mock Stop-Process):
# .\p02_usb_hf3_pid_safety_runtime_tests.ps1
```

Gates vật lý vẫn BLOCKED. Healthy Start ≠ frame USB.
