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
That release must **not** be used for Start/Stop until this safety corrective is applied.

## Verified COMPLETE (filled after packaging freeze + push)

Pin (packaging freeze): `PENDING_FREEZE`

Feature (PID safety corrective): `PENDING_FEATURE`

Pre-fix tip: `f441da40ade699021980ee636388be9eef42b68c`

Prior VT_BSTR freeze: `e18e3e234084bbc752366bbc22b011b416914115`

Baseline PR #26: `146d04cb930a446f891f48178a33672f0537b95e`

RAW URL / SHA256 / byte length: see tip commit after freeze (do not forge).

Owner (prepared HF3 — Update only; **no Start** until ChatGPT/audit OK):

```powershell
.\p02_usb_hf3_candidate_18878.ps1 -Mode Update -FullSourceZip <FULL.zip> -ExpectedSha256 <FULL_HEX>
.\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
.\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
.\p02_usb_hf3_pid_safety_runtime_tests.ps1
# Start only after independent audit + owner authorization
```
