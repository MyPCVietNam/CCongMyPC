# MyPC Attendance — P02-USB-HF3 COMPLETE AUDIT

PR #27 in-place corrective: COM **exactly-once** release + PS 5.1 Update leaf rename/rollback,
preserving IPropertyBag stage telemetry and strict DevicePath identity matching.

**Download:** `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip`

| Task alias | Archive member |
|------------|----------------|
| CHANGED-SOURCE-AUDIT.zip | `MyPC.Attendance-CHANGED-SOURCE-AUDIT-P02-USB-HF3.zip` (vs pre-fix `ff6789e`) |
| FULL-SOURCE.zip | `MyPC.Attendance-FULL-SOURCE-P02-USB-HF3.zip` |
| WINDOWS-SAFE-EVIDENCE.zip | `MYPC-P02-USB-HF3-WINDOWS-SAFE-EVIDENCE.zip` |
| COMPLETE-AUDIT.zip | `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip` |

Physical gates **BLOCKED**. Port `18878` HF3 DataDir only. Use `-Mode Update` on an already-prepared candidate — do **not** re-run Prepare.

## Verified COMPLETE (HTTP + SHA256 OK after push)

Pin (packaging freeze): `e0ad4aaca25bcbdeb8777bc6b509a518c97db1d2`

Feature (COM release fix): `22513784c91ccca764310e7d48953ce4a28c6ceb`

Pre-fix tip: `ff6789ecd15ede618101e6a4c4938c3290ed1748`

Property-bag prior tip: `05f6ba991b4b43b3719125551298b18441578bcb`

Baseline PR #26: `146d04cb930a446f891f48178a33672f0537b95e`

https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/e0ad4aaca25bcbdeb8777bc6b509a518c97db1d2/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip

SHA256 `00c8979d52187fbb218b8d31598de348c5cad1077cc805bea294fb49586c4d02` · **3800432** bytes

Inner:
- CHANGED `b5e1c5536b174840dd18bcbdbfc3905bd210ddd1e31af109299f173b26f7910f`
- FULL `8d8641b219a0a6eaca7e1eeee14b3187a0c7aa6cb8e68eaa35a96416a0ab80de`
- EVIDENCE `e0bb602acacf150c5f4c90b27c1646584a04aac84f034e775a900d8ac8ce8d1f`

```powershell
$u='https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/e0ad4aaca25bcbdeb8777bc6b509a518c97db1d2/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip'; $o="$env:TEMP\MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip"; Invoke-WebRequest -Uri $u -OutFile $o; (Get-FileHash $o -Algorithm SHA256).Hash.ToLower()
```

Expected hash: `00c8979d52187fbb218b8d31598de348c5cad1077cc805bea294fb49586c4d02`

Owner (prepared HF3 only — do not Prepare again):

```powershell
.\p02_usb_hf3_candidate_18878.ps1 -Mode Stop
.\p02_usb_hf3_candidate_18878.ps1 -Mode Update -FullSourceZip <FULL.zip> -ExpectedSha256 8d8641b219a0a6eaca7e1eeee14b3187a0c7aa6cb8e68eaa35a96416a0ab80de
.\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
.\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
# Start only when CAPTURE_MAPPING_VERIFIED=true and COM_RELEASE_WARNING_COUNT=0
.\p02_usb_hf3_candidate_18878.ps1 -Mode Start
.\p02_usb_hf3_candidate_18878.ps1 -Mode SafeExport
```
