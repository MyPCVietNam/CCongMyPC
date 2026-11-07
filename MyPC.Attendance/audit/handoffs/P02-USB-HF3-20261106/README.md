# MyPC Attendance — P02-USB-HF3 COMPLETE AUDIT

PR #27 in-place corrective: **PID safety V2** (Stop/Update/failure-cleanup) on top of
venv redirector ownership, preserving VT_BSTR Read / CoInit / COM release / identity.

**Download:** `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip`

| Task alias | Archive member |
|------------|----------------|
| CHANGED-SOURCE-AUDIT.zip | `MyPC.Attendance-CHANGED-SOURCE-AUDIT-P02-USB-HF3.zip` (vs pre-fix `f441da4`) |
| FULL-SOURCE.zip | `MyPC.Attendance-FULL-SOURCE-P02-USB-HF3.zip` |
| WINDOWS-SAFE-EVIDENCE.zip | `MYPC-P02-USB-HF3-WINDOWS-SAFE-EVIDENCE.zip` |
| COMPLETE-AUDIT.zip | `MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip` |

Physical gates **BLOCKED**. Port `18878` only. Use `-Mode Update` — do **not** Prepare.
**Do not Start** until independent audit of this corrective. Healthy Start ≠ USB frame / soak / CAMERA_LAB.

## Prior immutable pin (PID ownership V1 — superseded for Stop safety)

Packaging freeze: `59148ebd1d545aa887c4cb4a6288d9c8c394ba1b`  
Feature: `3c989facccc9443c351e0526dc76db7ee2f742a0`  
COMPLETE SHA256 `ddb9e7cd1afbe2661ba9bab1cc7de99fb419a695e43787c5f325c0846fc64e5e` · 3835525 bytes  
Do **not** Start/Stop that release without this safety corrective.

## Verified COMPLETE (HTTP + SHA256 OK after push)

Pin (packaging freeze): `0ea4264440bf330f005af7447bbd6bdb6cfabb46`

Feature (PID safety corrective): `ae003b8f703e62144feb1eed77e0462b536d74dd`

Pre-fix tip: `f441da40ade699021980ee636388be9eef42b68c`

Prior VT_BSTR freeze: `e18e3e234084bbc752366bbc22b011b416914115`

Baseline PR #26: `146d04cb930a446f891f48178a33672f0537b95e`

https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/0ea4264440bf330f005af7447bbd6bdb6cfabb46/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip

SHA256 `58017ee3f09b5e6f21dd6097c390058ff48616cf83cc8b1932e93a32627a0e6a` · **3873439** bytes

Inner:
- CHANGED `0c0a95f9ecfd1a6694db81b13ecae00a9969c3b6e88b4c3f51828aa4ae1ec37d`
- FULL `7bd8b000b43cbd832094582816f3c04a05af7585c934ed940c97623e85a10148`
- EVIDENCE `ca57c50e6fedf9202a9c352aea6ea25c826804f85668f91a8bb8f9cd0a64c97f`

```powershell
$u='https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/0ea4264440bf330f005af7447bbd6bdb6cfabb46/MyPC.Attendance/audit/handoffs/P02-USB-HF3-20261106/MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip'; $o="$env:TEMP\MYPC-P02-USB-HF3-COMPLETE-AUDIT.zip"; Invoke-WebRequest -Uri $u -OutFile $o; (Get-FileHash $o -Algorithm SHA256).Hash.ToLower()
```

Expected hash: `58017ee3f09b5e6f21dd6097c390058ff48616cf83cc8b1932e93a32627a0e6a`

Owner (prepared HF3 — Update only; **no Start** until ChatGPT/audit OK):

```powershell
.\p02_usb_hf3_candidate_18878.ps1 -Mode Update -FullSourceZip <FULL.zip> -ExpectedSha256 7bd8b000b43cbd832094582816f3c04a05af7585c934ed940c97623e85a10148
.\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
.\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
.\p02_usb_hf3_pid_safety_runtime_tests.ps1
# Start only after independent audit + owner authorization
```
