# MyPC Attendance — P02-USB-HF3 COMPLETE AUDIT

PR #27 in-place corrective: **PID safety V3** (mocked runtime harness, exact `--app-dir`,
fail-closed launcher Stop) on top of V2 ownership + COM/VT_BSTR/CoInit/identity.

**Download:** `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip`

| Task alias | Archive member |
|------------|----------------|
| CHANGED-SOURCE-AUDIT.zip | `MyPC.Attendance-CHANGED-SOURCE-AUDIT-P02-USB-HF3.zip` (vs pre-fix `a3b995e`) |
| FULL-SOURCE.zip | `MyPC.Attendance-FULL-SOURCE-P02-USB-HF3.zip` |
| WINDOWS-SAFE-EVIDENCE.zip | `MYPC-P02-USB-HF3-WINDOWS-SAFE-EVIDENCE.zip` |
| COMPLETE-AUDIT.zip | `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip` |

Physical gates **BLOCKED**. Port `18878` only. Use `-Mode Update` — do **not** Prepare.
**Do not Start / Stop / runtime harness** until independent audit of this V3 corrective.

## Prior immutable pin (PID safety V2 — superseded; harness unsafe)

Packaging freeze: `0ea4264440bf330f005af7447bbd6bdb6cfabb46`  
Feature: `ae003b8f703e62144feb1eed77e0462b536d74dd`  
COMPLETE SHA256 `58017ee3f09b5e6f21dd6097c390058ff48616cf83cc8b1932e93a32627a0e6a` · 3873439 bytes  
**Do not run** `p02_usb_hf3_pid_safety_runtime_tests.ps1` from that release on owner Windows.

## Verified COMPLETE (HTTP + SHA256 OK after push)

Pin (packaging freeze): `00858e3f78325517c43c4d688e5547748928b3a0`

Feature (PID safety V3): `97c1e9df2d54314098066eca7c88c7e82edc4c79`

Pre-fix tip: `a3b995ef4e78d67830192b22b2b6cc0e69a5beb5`

Baseline PR #26: `146d04cb930a446f891f48178a33672f0537b95e`

https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/00858e3f78325517c43c4d688e5547748928b3a0/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip

SHA256 `508f4fbc444f1ebb5fa7782a52ba8bb236448822e679718de344aeab10fce80f` · **3889380** bytes

Inner:
- CHANGED `3ca78a5ac4e0339517a7cf3fb76fdde7c9a86436960c6cc5f9b8b903aadcee45`
- FULL `1673aaedcbe16a53729cf1085a0a4afbcdaa645907b30c7d2ddeb0c759b37767`
- EVIDENCE `2943470ca499e0a6d7b4ab2638dea0c321ac621b672ef22e7e8c93fcb4755f25`

```powershell
$u='https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/00858e3f78325517c43c4d688e5547748928b3a0/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip'; $o="$env:TEMP\MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip"; Invoke-WebRequest -Uri $u -OutFile $o; (Get-FileHash $o -Algorithm SHA256).Hash.ToLower()
```

Expected hash: `508f4fbc444f1ebb5fa7782a52ba8bb236448822e679718de344aeab10fce80f`

Owner (Update only after independent V3 audit — no Start/Stop/runtime yet):

```powershell
.\p02_usb_hf3_candidate_18878.ps1 -Mode Update -FullSourceZip <FULL.zip> -ExpectedSha256 1673aaedcbe16a53729cf1085a0a4afbcdaa645907b30c7d2ddeb0c759b37767
.\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
.\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
```
