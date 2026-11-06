# MyPC Attendance — P02-USB-HF1 COMPLETE AUDIT

Corrective on PR #24: verified PnP↔DirectShow capture mapping + trust-preserving same-USB rebind.

**Download:** `MYPC-P02-USB-HF1-COMPLETE-AUDIT.zip`

Nested: CHANGED / FULL / WINDOWS-SAFE-EVIDENCE (named `*-P02-USB-HF1.zip`).

Physical gates remain **BLOCKED**. Candidate: `127.0.0.1:18878` only.

## Verified COMPLETE (HTTP + SHA256 OK)

Pin: `0510528dc6e56c67145432a184934b4080168cbe`

https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/0510528dc6e56c67145432a184934b4080168cbe/MyPC.Attendance/audit/handoffs/P02-USB-HF1-20261106/MYPC-P02-USB-HF1-COMPLETE-AUDIT.zip

SHA256 `cf05e215d3089ccd4411320eed28e50f82f2d704b020dad4003706c19c344b10` · **3806667** bytes

```powershell
$u='https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/0510528dc6e56c67145432a184934b4080168cbe/MyPC.Attendance/audit/handoffs/P02-USB-HF1-20261106/MYPC-P02-USB-HF1-COMPLETE-AUDIT.zip'; $o="$env:TEMP\MYPC-P02-USB-HF1-COMPLETE-AUDIT.zip"; Invoke-WebRequest -Uri $u -OutFile $o; (Get-FileHash $o -Algorithm SHA256).Hash.ToLower()
```
