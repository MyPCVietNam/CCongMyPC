# MyPC Attendance — P02-USB-HF3 COMPLETE AUDIT

PR #27 in-place corrective: DirectShow **IPropertyBag** property-bag reads + COM lifetime (STA worker), preserving strict DevicePath identity matching.

**Download:** `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip`

| Task alias | Archive member |
|------------|----------------|
| CHANGED-SOURCE-AUDIT.zip | `MyPC.Attendance-CHANGED-SOURCE-AUDIT-P02-USB-HF3.zip` (vs pre-fix `05f6ba9`) |
| FULL-SOURCE.zip | `MyPC.Attendance-FULL-SOURCE-P02-USB-HF3.zip` |
| WINDOWS-SAFE-EVIDENCE.zip | `MYPC-P02-USB-HF3-WINDOWS-SAFE-EVIDENCE.zip` |
| COMPLETE-AUDIT.zip | `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip` |

Physical gates **BLOCKED**. Port `18878` HF3 DataDir only. Use `-Mode Update` on an already-prepared candidate.

## Verified COMPLETE (HTTP + SHA256 OK)

Pin (packaging freeze): `6503df6893f43d93c211c9f96b80c11e5cc388fa`

Feature: `c765e3c2d4f5c8d78f11a597c43ddd4e86f66854`

Pre-fix tip: `05f6ba991b4b43b3719125551298b18441578bcb`

Baseline PR #26: `146d04cb930a446f891f48178a33672f0537b95e`

https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/6503df6893f43d93c211c9f96b80c11e5cc388fa/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip

SHA256 `e64a8281002c962ee54940e286106b23b985cb77b9ef724fb6eb46bfccf34869` · **3777597** bytes

```powershell
$u='https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/6503df6893f43d93c211c9f96b80c11e5cc388fa/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip'; $o="$env:TEMP\MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip"; Invoke-WebRequest -Uri $u -OutFile $o; (Get-FileHash $o -Algorithm SHA256).Hash.ToLower()
```

Expected hash: `e64a8281002c962ee54940e286106b23b985cb77b9ef724fb6eb46bfccf34869`
