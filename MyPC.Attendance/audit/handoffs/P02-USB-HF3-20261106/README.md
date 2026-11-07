# MyPC Attendance — P02-USB-HF3 COMPLETE AUDIT

PR #27 in-place corrective: **venv redirector PID ownership** for 18878 Start/Stop/Update,
preserving VT_BSTR Read / CoInit / COM release / identity fixes.

**Download:** `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip`

| Task alias | Archive member |
|------------|----------------|
| CHANGED-SOURCE-AUDIT.zip | `MyPC.Attendance-CHANGED-SOURCE-AUDIT-P02-USB-HF3.zip` (vs pre-fix `2fcb5bf`) |
| FULL-SOURCE.zip | `MyPC.Attendance-FULL-SOURCE-P02-USB-HF3.zip` |
| WINDOWS-SAFE-EVIDENCE.zip | `MYPC-P02-USB-HF3-WINDOWS-SAFE-EVIDENCE.zip` |
| COMPLETE-AUDIT.zip | `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip` |

Physical gates **BLOCKED**. Port `18878` only. Use `-Mode Update` — do **not** Prepare.
Healthy Start ≠ USB frame / soak / CAMERA_LAB.

## Verified COMPLETE (HTTP + SHA256 OK after push)

Pin (packaging freeze): `59148ebd1d545aa887c4cb4a6288d9c8c394ba1b`

Feature (PID ownership): `3c989facccc9443c351e0526dc76db7ee2f742a0`

Pre-fix tip: `2fcb5bf05cd61d47be93cbfbbbbb62ec4e16bddc`

Prior VT_BSTR freeze: `e18e3e234084bbc752366bbc22b011b416914115`

Baseline PR #26: `146d04cb930a446f891f48178a33672f0537b95e`

https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/59148ebd1d545aa887c4cb4a6288d9c8c394ba1b/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip

SHA256 `ddb9e7cd1afbe2661ba9bab1cc7de99fb419a695e43787c5f325c0846fc64e5e` · **3835525** bytes

Inner:
- CHANGED `d01bd31e9a283035228acf4e1e23416f99ee99370f986aaa3b4bb703b6727f11`
- FULL `4a847207a6076efe62921198ae6bee317443da12ff099ef4b602f08366f7bbd4`
- EVIDENCE `fda8559925ba3e750f8bd9157d5f8a750711717db9a261ed505e78474b93296a`

```powershell
$u='https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/59148ebd1d545aa887c4cb4a6288d9c8c394ba1b/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip'; $o="$env:TEMP\MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip"; Invoke-WebRequest -Uri $u -OutFile $o; (Get-FileHash $o -Algorithm SHA256).Hash.ToLower()
```

Expected hash: `ddb9e7cd1afbe2661ba9bab1cc7de99fb419a695e43787c5f325c0846fc64e5e`

Owner (prepared HF3 — do not Prepare; audit COMPLETE before Start if required):

```powershell
.\p02_usb_hf3_candidate_18878.ps1 -Mode Stop
.\p02_usb_hf3_candidate_18878.ps1 -Mode Update -FullSourceZip <FULL.zip> -ExpectedSha256 4a847207a6076efe62921198ae6bee317443da12ff099ef4b602f08366f7bbd4
.\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
.\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
.\p02_usb_hf3_candidate_18878.ps1 -Mode Start
```
