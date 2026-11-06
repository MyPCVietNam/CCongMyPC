# MyPC Attendance — P02-USB UVC COMPLETE AUDIT

Windows DirectShow USB UVC camera source alongside RTSP, LIVE provenance, independent trust subject (no EZVIZ HMAC inherit), CameraPage RTSP/USB UI, fake-device CI.

**Download:** `MYPC-P02-USB-UVC-COMPLETE-AUDIT.zip`

Nested: `CHANGED-SOURCE-AUDIT.zip`, `FULL-SOURCE.zip`, `WINDOWS-SAFE-EVIDENCE.zip`.

Physical gates remain **BLOCKED**. Candidate port for owner: `127.0.0.1:18878` with new DataDir — do not touch 18876/18877.

## Verified COMPLETE download (immutable)

Pin: `770185594812d567975054e00f331b991494ed44`

```
https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/770185594812d567975054e00f331b991494ed44/MyPC.Attendance/audit/handoffs/P02-USB-UVC-20261106/MYPC-P02-USB-UVC-COMPLETE-AUDIT.zip
```

SHA256: `1f391db8115a17c00e522933e9f5f86c5699ab849ec31c710ae873c3dc6cf1b1` (3794672 bytes)

PowerShell 5.1 verify:

```powershell
$u='https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/770185594812d567975054e00f331b991494ed44/MyPC.Attendance/audit/handoffs/P02-USB-UVC-20261106/MYPC-P02-USB-UVC-COMPLETE-AUDIT.zip'; $o="$env:TEMP\MYPC-P02-USB-UVC-COMPLETE-AUDIT.zip"; Invoke-WebRequest -Uri $u -OutFile $o; (Get-FileHash $o -Algorithm SHA256).Hash.ToLower()
# expect: 1f391db8115a17c00e522933e9f5f86c5699ab849ec31c710ae873c3dc6cf1b1
```
