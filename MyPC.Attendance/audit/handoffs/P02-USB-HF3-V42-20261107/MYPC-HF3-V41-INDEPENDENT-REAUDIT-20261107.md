# MyPC Attendance HF3 V4.1 - Independent Reaudit

Date: 2026-11-07 (Asia/Bangkok)
Verdict: **HOLD_CORRECTIVE** (do not approve Windows owner Prepare/Start/Stop/Update)
Audit target: uploaded MYPC-HF3-V41-COMPLETE-AUDIT.zip (immutable bytes)
Repository: https://github.com/MyPCVietNam/CCongMyPC ; PR #27

## 1. Provenance and custody

- COMPLETE SHA256: `ebcaf153c4eafa3c46646f2bd93f85c91b8823e9f8d64fb19619d8d1062b7654`
- Baseline V4 tip: `7c6a324da7a22c704b33a8ad1b0319099f38f1da`
- V4.1 feature SHA: `979349f52c755474ab3cecd7ab8c701bf43acd5b`
- Package/freeze SHA: `66abdc8664a43e82dba1592e4d276e58db270aea`
- Latest remote PR head observed: `a58659f53b31bfc053780b49973857d173c58dd9`
- Verified GitHub compare: feature -> freeze -> latest PR head changes only audit documentation/ZIP packaging, not the runtime PID/USB code. Do not conflate these pins.
- Full ZIP: 1,135 members; Changed ZIP: 34; Evidence ZIP: 25; COMPLETE: 27. All ZIP CRC/path-sensitive-name checks pass. All 34 Changed members match FULL bytes exactly. Manifest inventories match ZIP members exactly. Three nested ZIP SHA256 checks pass. Three evidence copies of core Windows files match FULL bytes.
- Eight core code file Git blob SHA1 checks matched GitHub immutable feature commit.
- `REMOTE_VERIFY.txt` bundled in uploaded COMPLETE still states `status=PENDING_PUSH` despite remote publication; this is a documentation/custody caveat, not a demonstrated code-tampering finding. Adjacent `SHA256SUMS-COMPLETE.txt` is not contained inside COMPLETE (self-referential checksum should remain external).

## 2. Test execution and evidence hierarchy

Independently executed on extracted uploaded FULL source (Linux / Python 3.13.5 / Node 22):
- `python quality_guard/check.py --root . --strict`: PASS (0 issues)
- `python -m unittest discover -s quality_guard/tests -p 'test_*.py' -q`: 22 PASS
- `node --test .cursor/hooks/guard-shell.test.cjs`: 23 PASS
- `python -m pytest -q MyPC.Attendance/tests/unit/test_p02_usb_hf3*.py`: 119 PASS
- Targeted additional residual canaries: 6 RED out of 6 (see independent_v41_residual_canaries.py; source-level analysis, not observed Windows crashes).
- Broader `pytest -m 'not real_model' tests/unit tests/integration tests/acceptance` did NOT finish within the local time limit (partial progress around 64%). It is **NOT** an independently witnessed full PASS. No Windows PowerShell executable is available in this audit container; PowerShell handler-level execution and physical USB are UNRUN locally.

GitHub Actions independently confirmed via GitHub API:
- Feature SHA `979349f`: run `https://github.com/MyPCVietNam/CCongMyPC/actions/runs/42366402413`: 4/4 PASS (frontend, backend-linux, windows-contract, guard-contract).
- Latest PR head `a58659f`: run `https://github.com/MyPCVietNam/CCongMyPC/actions/runs/42367094179`: 4/4 PASS.
- GitHub workflow PASS is real CI evidence; it is not a replacement for independent adversarial Windows-owner testing.

## 3. Findings requiring correction

### R9 - HIGH: Prepare can destroy existing source before proving process safety

File: `MyPC.Attendance/scripts/windows/p02_usb_hf3_candidate_18878.ps1`, lines 688-704, especially line 698.

After only checking FULL archive SHA, `Prepare` executes `if (Test-Path $srcDir) { Remove-Item -Recurse -Force $srcDir }` without a precondition that the HF3 process/port is absent or that this is a fresh install. It also deletes `srcDir` before validating that model source and required pins exist. Rerunning Prepare on a prepared/live candidate or with missing models can erase its source before a later failure. This is a code-flow finding, not a reproduced owner-machine deletion.

Required: fresh-only Prepare guard, immutable provenance preflight, check all required inputs *before* destructive actions; if src already exists, fail safely and direct to Update; ensure port/PID/metadata cannot be UNKNOWN or live, protect 18876/18877 and owner DataDirs, stage then promote atomically with rollback. Mock OS/file operations in CI.

### R10 - HIGH: inconsistent `uvicorn.pid` is ignored whenever valid launch metadata exists

File: same PowerShell script, Update lines 829-893, Start lines 983-1049.

For free port, Update checks `uvicorn.pid` only in `elseif (Test-Path -LiteralPath $pidFile)` when `$metaFree` is absent (lines 842, 871). Start similarly discards `uvicorn.pid` when `$prevFree` is valid (lines 995-1029) without first comparing it to both authenticated launcher/listener roles. A valid metadata record with an unexpected or unreadable PID file therefore bypasses PID record consistency validation. Treat unknown/mismatched files as evidence to preserve, not something to discard; no Start, Stop, Rename, or source promotion before resolving identity. This is source-level risk, not an observed live PID conflict.

Required: a reusable read-only consistency gate across all lifecycle modes; parse `uvicorn.pid` with strict encoding and integer validation, match allowed persisted PID roles for recorded state, probe identity/creation and fail closed on mismatch, unreadable or UNKNOWN. Only archive/clear after proving benign stale state; do not authorize via bare numeric PID.

### R11 - MEDIUM: Python ownership mirror accepts blank direct-process name

File: `MyPC.Attendance/scripts/windows/hf3_pid_ownership.py`, lines 311-316.

`classify_listener_ownership` returns DIRECT when listener.pid == launcher.pid and listener.name == ''. This is independently reproduced with a pure Python ProcessSnap input. PowerShell Test-IsPythonProcessName refuses blank names; harmonize Python mirror to fail closed. The mismatch is in the Python helper, not proof that PowerShell currently accepts blank process names.

### R12 - TEST-COVERAGE: V4.1 PowerShell handler harness duplicates production control-flow logic

File: `MyPC.Attendance/scripts/windows/p02_usb_hf3_v4_fail_closed_runtime_tests.ps1`, lines 101-163.

The harness extracts production helper functions but creates its own `Invoke-Hf3StartHandler`, `Invoke-Hf3UpdateHandler` and `Invoke-Hf3StopHandler` bodies. These facades are not defined in the actual production script. Therefore green facade assertions do not prove execution of the real `switch ($Mode)` branches. Refactor production preflight decisions into common pure handler functions or safely extract/test actual production handler logic under injected OS mocks. Never let the synthetic suite reach real Stop-Process or any real/injected owner PID.

## 4. Gate matrix

| Gate | Audit classification | Basis |
|---|---|---|
| GUARD_FRAMEWORK | PASS | strict guard + 22 tests |
| BACKEND_CI | PASS | GitHub Actions `backend-linux` on immutable feature and latest head |
| FRONTEND_CI | PASS | GitHub Actions `frontend` on immutable feature and latest head |
| WINDOWS_CODE | BLOCKED | Windows CI success, but independent R9/R10 lifecycle gaps and R12 coverage |
| USB_WINDOWS_PHYSICAL | BLOCKED | no real UGREEN frame / owner evidence |
| USB_STABILITY_30_MIN | BLOCKED | no 30-minute real USB soak and reconnect evidence |
| USB_CAMERA_LAB_OWNER_SIGN | BLOCKED | no explicit owner sign-off on this revision |
| FACE_PILOT | BLOCKED | not yet validated with real enrolled volunteers |
| INSTALLER | BLOCKED | no installer acceptance |
| PRODUCTION_READY | BLOCKED | preceding gates unresolved |

Overall verdict: HOLD_CORRECTIVE. The focused R1-R8 patch is a substantial improvement, but the system must not be installed/started/updated on the owner Windows environment on this evidence alone.

## 5. Handoff requirements for Cursor

Use `MYPC-HF3-V42-PREPARE-PID-RECORD-GUARD-CURSOR-EN.md`. Apply the project's `/mypc-safe-change` workflow, make R9-R12 RED on prior SHA then GREEN after corrective (without weakening assertions), run GitHub Windows 5.1 CI/backend/frontend/guard, and deliver FOUR FULL/CHANGED/EVIDENCE/COMPLETE ZIP archives with per-file SHA256, relative manifest, commit pins, a separate COMPLETE checksum sidecar, and truthful physical gate BLOCKED statuses. PR #27 remains unmerged pending owner authorization.

No user biometric data, RTSP credentials, HMAC keys, DataDir, owner 18876/18877 processes, or USB physical devices were accessed by this audit.
