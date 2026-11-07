# HF3 V4.2 — Prepare Safety + PID Record Consistency

## Verdict

**READY_FOR_INDEPENDENT_REAUDIT** (not `OWNER_START_APPROVED`).

Physical / camera / soak / installer / production gates remain **BLOCKED** without fresh owner evidence.

## Custody (do not conflate)

| Role | SHA |
|------|-----|
| V4.1 tested feature (R9–R12 RED baseline) | `979349f52c755474ab3cecd7ab8c701bf43acd5b` |
| V4.1 packaging freeze | `66abdc8664a43e82dba1592e4d276e58db270aea` |
| V4.1 COMPLETE SHA256 | `ebcaf153c4eafa3c46646f2bd93f85c91b8823e9f8d64fb19619d8d1062b7654` |
| Prior PR tip (docs after V4.1 feature) | `a58659f53b31bfc053780b49973857d173c58dd9` |
| V4.2 feature (code) | see `FEATURE_COMMIT.txt` |
| V4.2 packaging freeze | see `PACKAGING_FREEZE_COMMIT.txt` |
| Final remote PR tip | see `REMOTE_PR_TIP.txt` |

PR: https://github.com/MyPCVietNam/CCongMyPC/pull/27  
Branch: `cursor/p02-usb-hf3-dshow-com-enum-83a8`  
Isolated candidate port: `127.0.0.1:18878` (never 18876/18877).

## Archives

1. `MyPC.Attendance-FULL-SOURCE-HF3-V42.zip`
2. `MyPC.Attendance-CHANGED-SOURCE-AUDIT-HF3-V42.zip`
3. `MYPC-HF3-V42-WINDOWS-SAFE-EVIDENCE.zip`
4. `MYPC-HF3-V42-COMPLETE-AUDIT.zip`

Authoritative COMPLETE digest lives in **sidecar** `SHA256SUMS-COMPLETE.txt` (not inside COMPLETE).

## Scope (R9–R12)

- **R9** Prepare: authorize before mutation; stage-then-promote; refuse existing src / live listener / bad root / missing models.
- **R10** Shared `Get-Hf3PidRecordState` / `Test-Hf3PidRecord` on Start/Stop/Update free and occupied paths.
- **R11** Python `DIRECT` requires `is_python_process(listener.name)` (blank/conhost → UNVERIFIED).
- **R12** Production `Invoke-Hf3*Handler` extracted into injected PS 5.1 harness (no synthetic facades).

## Owner instruction

Do **not** run Prepare/Start/Stop/Update until independent reaudit of this COMPLETE ZIP and explicit approval. See `OWNER_RUNBOOK_VI.md`.
