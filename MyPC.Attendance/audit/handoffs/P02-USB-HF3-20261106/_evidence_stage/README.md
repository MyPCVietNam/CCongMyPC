# MyPC Attendance — P02-USB-HF3 COMPLETE AUDIT

Corrective on PR #26: native DirectShow COM video enumeration + DevicePath↔PnP verified binding.

**Download:** `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip`

| Task alias | Archive member |
|------------|----------------|
| CHANGED-SOURCE-AUDIT.zip | `MyPC.Attendance-CHANGED-SOURCE-AUDIT-P02-USB-HF3.zip` |
| FULL-SOURCE.zip | `MyPC.Attendance-FULL-SOURCE-P02-USB-HF3.zip` |
| WINDOWS-SAFE-EVIDENCE.zip | `MYPC-P02-USB-HF3-WINDOWS-SAFE-EVIDENCE.zip` |
| COMPLETE-AUDIT.zip | `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip` |

Physical gates **BLOCKED**. Port `18878` HF3 DataDir only.

## Verified COMPLETE (HTTP + SHA256 OK)

Pin (ZIP-introducing packaging freeze): `91a7c3188af67da1234a099c60756b4d062b638b`

Feature / source freeze tree: `53bf5919a1192d1e4e0d69e60a12274de7fda7e9`

Baseline PR #26: `146d04cb930a446f891f48178a33672f0537b95e`

https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/91a7c3188af67da1234a099c60756b4d062b638b/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip

SHA256 `23315ef1d7935475a63b75cc31901371ec18a0c74f1d333eabb4ac0a80ec4fb3` · **3785256** bytes

```powershell
$u='https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/91a7c3188af67da1234a099c60756b4d062b638b/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip'; $o="$env:TEMP\MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip"; Invoke-WebRequest -Uri $u -OutFile $o; (Get-FileHash $o -Algorithm SHA256).Hash.ToLower()
```

Expected hash: `23315ef1d7935475a63b75cc31901371ec18a0c74f1d333eabb4ac0a80ec4fb3`
