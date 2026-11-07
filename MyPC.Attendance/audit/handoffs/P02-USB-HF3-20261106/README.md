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

## Verified COMPLETE (filled after packaging freeze + push)

Pin (packaging freeze): see tip commit after freeze (immutable Git SHA of ZIP commit).

Feature (PID safety V3): filled at feature commit.

Pre-fix tip: `a3b995ef4e78d67830192b22b2b6cc0e69a5beb5`

Baseline PR #26: `146d04cb930a446f891f48178a33672f0537b95e`

Owner after V3 freeze (Update only):

```powershell
.\p02_usb_hf3_candidate_18878.ps1 -Mode Update -FullSourceZip <FULL.zip> -ExpectedSha256 <FULL_HEX>
.\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
.\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
```
