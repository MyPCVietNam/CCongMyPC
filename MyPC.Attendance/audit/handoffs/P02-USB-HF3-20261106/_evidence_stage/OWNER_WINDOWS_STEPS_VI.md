# P02-USB-HF3 — Owner Windows (PID ownership fix)

**KHÔNG** Prepare. **KHÔNG** đụng 18876/18877.

```powershell
cd <extract>\MyPC.Attendance\scripts\windows
.\p02_usb_hf3_candidate_18878.ps1 -Mode Stop
.\p02_usb_hf3_candidate_18878.ps1 -Mode Update `
  -FullSourceZip <FULL.zip> -ExpectedSha256 <hex>
.\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
.\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
# Chỉ Start sau khi Diagnose mapping PASS:
.\p02_usb_hf3_candidate_18878.ps1 -Mode Start
```

Log kỳ vọng khi Start PASS:
- `ownership_probe rel=DIRECT|VERIFIED_DESCENDANT`
- `HEALTH READY ownership=... listener_pid=...`
- `uvicorn.launch.json` được ghi

Nếu FAIL: mã `EXIT_LISTENER_OWNERSHIP` / `EXIT_HEALTH_NOT_READY` /
`EXIT_FOREIGN_LISTENER` / `EXIT_AMBIGUOUS_LISTENERS` — không kill process lạ.

Healthy Start **không** chứng minh frame USB; gates vật lý vẫn BLOCKED.
