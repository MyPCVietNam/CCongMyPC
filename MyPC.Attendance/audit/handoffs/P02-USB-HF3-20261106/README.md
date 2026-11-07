# MyPC Attendance — P02-USB-HF3 COMPLETE AUDIT

PR #27 in-place: **Engineering Quality Guard v1.0** on PID safety V3
(mocked Stop-Process harness, exact `--app-dir`, fail-closed Stop) + COM/VT_BSTR/identity.

**Download:** `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip`

| Task alias | Archive member |
|------------|----------------|
| CHANGED-SOURCE-AUDIT.zip | `MyPC.Attendance-CHANGED-SOURCE-AUDIT-P02-USB-HF3.zip` (vs `ab1161d`) |
| FULL-SOURCE.zip | `MyPC.Attendance-FULL-SOURCE-P02-USB-HF3.zip` (includes repo-root Quality Guard) |
| WINDOWS-SAFE-EVIDENCE.zip | `MYPC-P02-USB-HF3-WINDOWS-SAFE-EVIDENCE.zip` |
| COMPLETE-AUDIT.zip | `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip` |

Physical gates **BLOCKED**. **Do not Start / Stop / runtime harness.**
GitHub Actions jobs are **UNRUN** until run links appear — do not treat agent-local PASS as Actions PASS.

## Prior immutable pins

- V3 freeze `00858e3f78325517c43c4d688e5547748928b3a0` COMPLETE `508f4fbc…`
- V2 freeze `0ea4264440bf330f005af7447bbd6bdb6cfabb46` COMPLETE `58017ee3…` (harness unsafe)
- V3 feature `97c1e9df2d54314098066eca7c88c7e82edc4c79`

## Verified COMPLETE (HTTP + SHA256 OK after push)

Pin (packaging freeze): `66de411f35bcb2f4c011568524d7b0ce7fea9684`

Feature (Quality Guard + packager): `51b2ee92270b0ce7ed031b4f4d829a69dcb9744c`

Overlay feature: `daef3836b8ff8542ffff64e16959c778b5dce311`

Pre-fix tip: `ab1161dd87f0f363ea3974cf68c79b095ec11f03`

https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/66de411f35bcb2f4c011568524d7b0ce7fea9684/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip

SHA256 `63dd0a57c1c3247b841e16e5e7e8aef93c3b521b55442be369ef2d2b849b03e0` · **3959471** bytes

Inner:
- CHANGED `962794308d728af9d1a8e079b4ab1f96ed99946d7b68d545fe123a219c1bcd64`
- FULL `af967cdde50c4c9691dc245897fca8c2eb23098bfe4991c8f871452f14660760`
- EVIDENCE `c42252c95d1f4e9ffc140e4dc90303196f3a55278dd20c2de7f1c3daa1e95521`

```powershell
$u='https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/66de411f35bcb2f4c011568524d7b0ce7fea9684/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip'; $o="$env:TEMP\MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip"; Invoke-WebRequest -Uri $u -OutFile $o; (Get-FileHash $o -Algorithm SHA256).Hash.ToLower()
```

Expected hash: `63dd0a57c1c3247b841e16e5e7e8aef93c3b521b55442be369ef2d2b849b03e0`

Owner (Update only after audit; no Start/Stop/runtime):

```powershell
.\p02_usb_hf3_candidate_18878.ps1 -Mode Update -FullSourceZip <FULL.zip> -ExpectedSha256 af967cdde50c4c9691dc245897fca8c2eb23098bfe4991c8f871452f14660760
.\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
.\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
```
