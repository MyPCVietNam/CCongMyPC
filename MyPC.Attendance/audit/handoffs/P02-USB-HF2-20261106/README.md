# MyPC Attendance — P02-USB-HF2 COMPLETE AUDIT

Corrective on PR #25: verified UVC source binding (no fabricated mapping), CAP_DSHOW index-only open, stale-index clear, working 18878 candidate launcher.

**Download:** `MYPC-P02-USB-HF2-COMPLETE-AUDIT.zip`

Nested naming (task aliases → archive members):

| Task name | Archive member |
|-----------|----------------|
| MYPC-P02-USB-HF2-CHANGED-SOURCE-AUDIT.zip | `MyPC.Attendance-CHANGED-SOURCE-AUDIT-P02-USB-HF2.zip` |
| MYPC-P02-USB-HF2-FULL-SOURCE.zip | `MyPC.Attendance-FULL-SOURCE-P02-USB-HF2.zip` |
| MYPC-P02-USB-HF2-WINDOWS-SAFE-EVIDENCE.zip | same |
| MYPC-P02-USB-HF2-COMPLETE-AUDIT.zip | same (outer) |

Physical gates remain **BLOCKED**. Candidate: `127.0.0.1:18878` only. Never claim index 2 as stable hardware identity.

## Verified COMPLETE (HTTP + SHA256 OK)

Pin (ZIP-introducing packaging freeze): `9d5a2477a174a52497b798c6f6c4ddfb531a2fa9`

Feature / source freeze tree: `64e370f4db368da2da4f89800802855b24960d5d`

Baseline PR #25: `6d1842b5c2bd577f4945f35e85767228906fae0d`

https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/9d5a2477a174a52497b798c6f6c4ddfb531a2fa9/MyPC.Attendance/audit/handoffs/P02-USB-HF2-20261106/MYPC-P02-USB-HF2-COMPLETE-AUDIT.zip

SHA256 `12c7b0300eb7e90757c050a86de65608409fe5152c1b7d00df0985cd3844c808` · **3840531** bytes

```powershell
$u='https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/9d5a2477a174a52497b798c6f6c4ddfb531a2fa9/MyPC.Attendance/audit/handoffs/P02-USB-HF2-20261106/MYPC-P02-USB-HF2-COMPLETE-AUDIT.zip'; $o="$env:TEMP\MYPC-P02-USB-HF2-COMPLETE-AUDIT.zip"; Invoke-WebRequest -Uri $u -OutFile $o; (Get-FileHash $o -Algorithm SHA256).Hash.ToLower()
```

Expected hash: `12c7b0300eb7e90757c050a86de65608409fe5152c1b7d00df0985cd3844c808`
