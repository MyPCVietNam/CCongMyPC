# MyPC Attendance — P02-USB-HF3 COMPLETE AUDIT

Corrective on PR #26 + **in-place identity patch on PR #27**: native DirectShow COM enum and **strict** DevicePath↔PnP video-function binding.

**Download:** `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip`

| Task alias | Archive member |
|------------|----------------|
| CHANGED-SOURCE-AUDIT.zip | `MyPC.Attendance-CHANGED-SOURCE-AUDIT-P02-USB-HF3.zip` |
| FULL-SOURCE.zip | `MyPC.Attendance-FULL-SOURCE-P02-USB-HF3.zip` |
| WINDOWS-SAFE-EVIDENCE.zip | `MYPC-P02-USB-HF3-WINDOWS-SAFE-EVIDENCE.zip` |
| COMPLETE-AUDIT.zip | `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip` |

Physical gates **BLOCKED**. Port `18878` HF3 DataDir only.

## Verified COMPLETE (HTTP + SHA256 OK)

Pin (ZIP-introducing packaging freeze): `c951b2abeabb82ae4141f41a94d20070be9e1487`

Feature / source freeze tree: `058481f9989b0126648fc64bc14507f638057dd4`

Baseline PR #26: `146d04cb930a446f891f48178a33672f0537b95e`

https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/c951b2abeabb82ae4141f41a94d20070be9e1487/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip

SHA256 `19f17e5eca907adf32e6043c3e3b7b30bcbda504fca858a2e9d29b15651ac2b9` · **3839797** bytes

```powershell
$u='https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/c951b2abeabb82ae4141f41a94d20070be9e1487/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip'; $o="$env:TEMP\MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip"; Invoke-WebRequest -Uri $u -OutFile $o; (Get-FileHash $o -Algorithm SHA256).Hash.ToLower()
```

Expected hash: `19f17e5eca907adf32e6043c3e3b7b30bcbda504fca858a2e9d29b15651ac2b9`
