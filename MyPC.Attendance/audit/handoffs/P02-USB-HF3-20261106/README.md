# MyPC Attendance — P02-USB-HF3 COMPLETE AUDIT

PR #27 in-place corrective: comtypes 1.4.17 **`CoInitializeEx(flags)`** signature +
`DSHOW_COINIT_FAILED` classification, preserving prior COM release / Update / identity fixes.

**Download:** `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip`

| Task alias | Archive member |
|------------|----------------|
| CHANGED-SOURCE-AUDIT.zip | `MyPC.Attendance-CHANGED-SOURCE-AUDIT-P02-USB-HF3.zip` (vs pre-fix `98d8d40`) |
| FULL-SOURCE.zip | `MyPC.Attendance-FULL-SOURCE-P02-USB-HF3.zip` |
| WINDOWS-SAFE-EVIDENCE.zip | `MYPC-P02-USB-HF3-WINDOWS-SAFE-EVIDENCE.zip` |
| COMPLETE-AUDIT.zip | `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip` |

Physical gates **BLOCKED**. Port `18878` only. Use `-Mode Update` — do **not** re-run Prepare.

## Verified COMPLETE (HTTP + SHA256 OK after push)

Pin (packaging freeze): `bd8aaf08651d2039a5e3a25f6ea7b88f1adf95f0`

Feature (CoInit signature): `29e76e466026b17f9cb2a06c71dce7c9820518cf`

Pre-fix tip: `98d8d40290018d688749931a9f78d4ee016b126b`

Prior COM-release freeze: `e0ad4aaca25bcbdeb8777bc6b509a518c97db1d2`

Baseline PR #26: `146d04cb930a446f891f48178a33672f0537b95e`

https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/bd8aaf08651d2039a5e3a25f6ea7b88f1adf95f0/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip

SHA256 `027b8b6fc0f83ad01a1a617d0e41a617ed243e1601962cc654a19bbcbedf84c1` · **3799067** bytes

Inner:
- CHANGED `f3242596ca61ff3a700394e0f404bccf5d5071ddda2fc7c4c28374a4c7ccdf2b`
- FULL `00359f5ec679dcbaca5e29354044be7edf8c84cd889746bde275199b8a5db265`
- EVIDENCE `fd856daa1f06aac1c74e51a07cfda3b1dddc2a843eec8d81f86a54bdb89d89d3`

```powershell
$u='https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/bd8aaf08651d2039a5e3a25f6ea7b88f1adf95f0/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip'; $o="$env:TEMP\MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip"; Invoke-WebRequest -Uri $u -OutFile $o; (Get-FileHash $o -Algorithm SHA256).Hash.ToLower()
```

Expected hash: `027b8b6fc0f83ad01a1a617d0e41a617ed243e1601962cc654a19bbcbedf84c1`

Owner (prepared HF3 only — do not Prepare again):

```powershell
.\p02_usb_hf3_candidate_18878.ps1 -Mode Stop
.\p02_usb_hf3_candidate_18878.ps1 -Mode Update -FullSourceZip <FULL.zip> -ExpectedSha256 00359f5ec679dcbaca5e29354044be7edf8c84cd889746bde275199b8a5db265
.\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
.\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
```
