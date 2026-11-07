# P02-USB-HF3 — Owner Windows (PID safety corrective V2)

**KHÔNG** Prepare. **KHÔNG** đụng 18876/18877 / DataDir / venv / model / HMAC.  
**KHÔNG** Start cho đến khi audit độc lập xác nhận bản corrective này.

```powershell
cd <extract>\MyPC.Attendance\scripts\windows
# Nếu đang chạy bản cũ và Stop fail-closed: giữ uvicorn.launch.json để điều tra.
.\p02_usb_hf3_candidate_18878.ps1 -Mode Update `
  -FullSourceZip <FULL.zip> -ExpectedSha256 <hex>
.\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
.\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
.\p02_usb_hf3_pid_safety_runtime_tests.ps1
# Start CHỈ sau audit + CAPTURE_MAPPING_VERIFIED=true + ủy quyền owner:
# .\p02_usb_hf3_candidate_18878.ps1 -Mode Start
# .\p02_usb_hf3_candidate_18878.ps1 -Mode Stop
```

Stop fail-closed (giữ evidence): `EXIT_STOP_BLOCKED_LEGACY_PID` /
`EXIT_FOREIGN_LISTENER` / `EXIT_AMBIGUOUS_LISTENERS` / `EXIT_STOP_INCOMPLETE` /
`EXIT_STOP_BLOCKED`.

Healthy Start **không** chứng minh frame USB; gates vật lý vẫn BLOCKED.
