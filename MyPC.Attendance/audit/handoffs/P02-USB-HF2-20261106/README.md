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

## Verified COMPLETE (filled after packaging pin)

See `PACKAGE_META.json` / commit message after freeze sidecar. Replace placeholders below once HTTP GET of raw URL succeeds.

Pin: `<PACKAGING_FREEZE_OR_URL_SIDECAR>`

https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/<PIN>/MyPC.Attendance/audit/handoffs/P02-USB-HF2-20261106/MYPC-P02-USB-HF2-COMPLETE-AUDIT.zip

SHA256 `<OUTER_SHA256>` · **`<BYTES>`** bytes

```powershell
$u='https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/<PIN>/MyPC.Attendance/audit/handoffs/P02-USB-HF2-20261106/MYPC-P02-USB-HF2-COMPLETE-AUDIT.zip'; $o="$env:TEMP\MYPC-P02-USB-HF2-COMPLETE-AUDIT.zip"; Invoke-WebRequest -Uri $u -OutFile $o; (Get-FileHash $o -Algorithm SHA256).Hash.ToLower()
```
