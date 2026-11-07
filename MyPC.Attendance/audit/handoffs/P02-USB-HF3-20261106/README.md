# MyPC Attendance — P02-USB-HF3 COMPLETE AUDIT

PR #27 in-place corrective: IPropertyBag **`VT_BSTR` + direct VARIANT** Read,
preserving CoInit/release/Update/identity fixes.

**Download:** `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip`

| Task alias | Archive member |
|------------|----------------|
| CHANGED-SOURCE-AUDIT.zip | `MyPC.Attendance-CHANGED-SOURCE-AUDIT-P02-USB-HF3.zip` (vs pre-fix `aa0c385`) |
| FULL-SOURCE.zip | `MyPC.Attendance-FULL-SOURCE-P02-USB-HF3.zip` |
| WINDOWS-SAFE-EVIDENCE.zip | `MYPC-P02-USB-HF3-WINDOWS-SAFE-EVIDENCE.zip` |
| COMPLETE-AUDIT.zip | `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip` |

Physical gates **BLOCKED**. Port `18878` only. Use `-Mode Update` — do **not** Prepare.

## Verified COMPLETE (HTTP + SHA256 OK after push)

Pin (packaging freeze): `e18e3e234084bbc752366bbc22b011b416914115`

Feature (VT_BSTR direct Read): `d173b021c4b1e613b2ad8afe987244ffa8a5e702`

Pre-fix tip: `aa0c385f414d410d2c6aa0cdec7d676fb8f2ac7e`

Prior CoInit freeze: `bd8aaf08651d2039a5e3a25f6ea7b88f1adf95f0`

Baseline PR #26: `146d04cb930a446f891f48178a33672f0537b95e`

https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/e18e3e234084bbc752366bbc22b011b416914115/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip

SHA256 `929af655f32c3bd4d0ca4644179ec83d2936de2bb883543a14cbac04f4a85985` · **3811173** bytes

Inner:
- CHANGED `8822e1ec135ba8032c8c72c895cb66a040f1181cb11e5af03f760e36e8218b14`
- FULL `f65ded14ed2d3319c1c11957b17298e259a4db82036afa98bbe1abdfb20b1e3c`
- EVIDENCE `65a56329db141c3358bcef84fc0d605359a48024cb5d93b2dfe4bd5a9c896cc9`

```powershell
$u='https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/e18e3e234084bbc752366bbc22b011b416914115/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip'; $o="$env:TEMP\MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip"; Invoke-WebRequest -Uri $u -OutFile $o; (Get-FileHash $o -Algorithm SHA256).Hash.ToLower()
```

Expected hash: `929af655f32c3bd4d0ca4644179ec83d2936de2bb883543a14cbac04f4a85985`

Owner (prepared HF3 only — do not Prepare):

```powershell
.\p02_usb_hf3_candidate_18878.ps1 -Mode Stop
.\p02_usb_hf3_candidate_18878.ps1 -Mode Update -FullSourceZip <FULL.zip> -ExpectedSha256 f65ded14ed2d3319c1c11957b17298e259a4db82036afa98bbe1abdfb20b1e3c
.\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
.\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
```
