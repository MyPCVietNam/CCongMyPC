# P02-USB-HF3 — Hướng dẫn Windows

1. Tải COMPLETE ZIP (pin + SHA256 trong README).
2. Prepare/Preflight/Diagnose/Start trên **DataDir HF3 mới** (không đụng HF2/HF5):

```powershell
.\p02_usb_hf3_candidate_18878.ps1 -Mode Prepare -FullSourceZip <FULL> -ExpectedSha256 <hex> -ModelsSourceDir <onnx>
.\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
.\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
# Kỳ vọng: DSHOW_VIDEO_MONIKER_COUNT>0; CAPTURE_MAPPING_VERIFIED=true; không còn 0x800401F3
.\p02_usb_hf3_candidate_18878.ps1 -Mode Start
Invoke-WebRequest http://127.0.0.1:18878/api/v1/health
```

3. Smoke: 1080p → unplug/replug → dual tab → soak 30′ → USB CAMERA_LAB **mới**.
4. SafeExport chỉ log redacted.

Gates vật lý vẫn BLOCKED cho đến khi owner xác nhận Diagnose/Start.
