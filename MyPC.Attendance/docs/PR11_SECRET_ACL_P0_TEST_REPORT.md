# Secrets ACL P0 corrective — test report

**Branch:** `cursor/pr11-secret-acl-hf-83a8`  
**Base Camera/RTSP HF:** `4ec06cf`  
**Do not merge into main.**

## Defects closed in source

| ID | Defect | Fix |
|----|--------|-----|
| A | `$home =` → `VariableNotWritable` on Windows PowerShell 5.1 | Renamed to `$attendanceHome` in both PS1 scripts; UTF-8 BOM retained |
| B | Literal `S-1-…` search in `icacls` text | `GetNamedSecurityInfo` → SID AceInfo; PS uses `Get-Acl` + `Translate` to SID |
| C | Weak repair pre-checks | App-stopped, ACL `/save`, critical backup validation, allowlist-only, no Everyone, no content rewrite |

## Linux results (this environment)

| Case | Result |
|------|--------|
| `tests/unit/test_pr11_secrets_acl.py` (16) | PASS |
| Full pytest | **273 passed** |
| Static PS1: no `$home=`, has `$attendanceHome`, UTF-8 BOM | PASS |
| Idempotent `ensure_secrets_dir_acl` when healthy | PASS (mocked Win32) |
| Unhealthy → apply `(OI)(CI)` + post-check | PASS (mocked) |

## Windows PowerShell 5.1 / physical gate

| Case | Result |
|------|--------|
| Parse/execute Repair script under Windows PS 5.1 as `LONGKYTHUAT-MYP\MyPC` | **BLOCKED** — no Windows host in cloud agent |
| Read-only audit / scoped repair / non-elevated re-read | **BLOCKED** |
| SID + `(OI)(CI)` verification on real ACL | **BLOCKED** |
| Three successive app restarts, same DataDir | **BLOCKED** |
| Admin login + camera decrypt + content vs backup | **BLOCKED** |
| Idempotent startup (no unnecessary `/inheritance:r`) | **BLOCKED** |
| SID-form and DOMAIN\\User icacls display both healthy | **BLOCKED** |

Owner must run `docs/vi/SECRETS_ACL_WINDOWS.md` and attach evidence before acceptance.
Linux unit tests do **not** substitute for Windows ACL tests.

## Commands (owner Windows)

```powershell
.\scripts\windows\Repair-MyPCSecretsAcl.ps1 -CheckOnly
# elevated, same MyPC account:
.\scripts\windows\Repair-MyPCSecretsAcl.ps1 -Repair
.\scripts\windows\Repair-MyPCSecretsAcl.ps1 -CheckOnly
.\scripts\windows\Start-MyPCAttendance.ps1 -DataDir "$env:LOCALAPPDATA\MyPC\Attendance\data"
# repeat start 3x; confirm Admin login + camera decrypt
```
