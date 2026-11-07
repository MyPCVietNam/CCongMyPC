# Independent adversarial review — HF3 PID Safety V4 fail-closed

| Field | Value |
|-------|-------|
| Reviewer | Independent subagent (code-only; not the implementing agent) |
| Branch | `cursor/p02-usb-hf3-dshow-com-enum-83a8` (stayed; no checkout/push) |
| Immutable baseline tip | `8dc2dfed68464eb7ba98db6fc4efae90ee3f07a4` |
| Scope reviewed | Working-tree V4 corrective on tip (modified/untracked paths below) |
| Reviewed at | 2026-11-07T09:11Z |
| Classification | SECURITY_SENSITIVE + WINDOWS_HOST (mocked only here) |

**Reviewed paths**

- `MyPC.Attendance/scripts/windows/p02_usb_hf3_candidate_18878.ps1`
- `MyPC.Attendance/tests/unit/test_p02_usb_hf3_v4_fail_closed.py`
- `MyPC.Attendance/scripts/windows/p02_usb_hf3_v4_fail_closed_runtime_tests.ps1`
- `quality_guard/check.py` V4 gates (+ `quality_guard/tests/test_hf3_safety.py`, PS QualityGuard tests)

**Baseline contrast:** `V4_INDEPENDENT_INVARIANT_RED.json` / `V4_BEHAVIORAL_BASELINE_RED.txt` show tip `8dc2dfe` failing F-01..F-06 and related contracts (10 failed / 2 passed). Working-tree corrective flips those source contracts green.

---

## Code-only verdict: **PASS**

F-01..F-06 closures hold under adversarial static review and Linux-executable contracts. UNKNOWN≠ABSENT and INVALID≠ABSENT are enforced on kill/start/update authorization paths. Listener Python-name gate, no-real-kill test posture, and `--app-dir` space quoting are present.

**Physical / owner-host gates remain BLOCKED** (see below). This PASS is not a Windows runtime or owner-lab clearance.

---

## F-01 .. F-06 closures

| ID | Claim | Code finding | Verdict |
|----|--------|--------------|---------|
| **F-01** | Start blocks malformed meta when port free | Free-port Start calls `Get-Hf3LaunchMetaState`; `INVALID` → `EXIT_START_INVALID_LAUNCH_META` before any `Start-Process` / meta `Remove-Item` | **CLOSED** |
| **F-02** | Update blocks malformed meta when port free | Free-port Update: `INVALID` → discard staged ZIP only → `EXIT_UPDATE_INVALID_LAUNCH_META`; launch meta preserved | **CLOSED** |
| **F-03** | Update free-port checks listener as well as launcher | Free-port loop probes both `launcher_*` and `listener_*`; live listener → `EXIT_UPDATE_STALE_LISTENER` | **CLOSED** |
| **F-04** | Process probe UNKNOWN ≠ ABSENT | `Get-Win32ProcessById`: `-ErrorAction Stop`; catch → `EXIT_PROCESS_PROBE_UNKNOWN`. No `SilentlyContinue` in helper | **CLOSED** |
| **F-05** | TCP probe UNKNOWN ≠ free port | `Get-Hf3PortListenerOwnerPids`: Stop + throw `EXIT_TCP_PROBE_UNKNOWN` except explicit empty-listener message patterns → `@()` | **CLOSED** |
| **F-06** | Stop corrupt meta ≠ “nothing to stop” | Stop: `INVALID` → `EXIT_STOP_INVALID_LAUNCH_META` **before** ABSENT / “nothing to stop” | **CLOSED** |

Independent invariant re-probe (source-level, post-corrective): all six checks **true**; `Read-Hf3LaunchMeta` throws on INVALID (no longer silent `$null`).

---

## Cross-cutting invariants

### UNKNOWN ≠ ABSENT

- `Get-Win32ProcessById`: provider failure throws; missing process returns `$null`.
- `Stop-VerifiedHf3Identity`: catch on probe → log “process probe UNKNOWN (not treated as absent)” → `$false` (no kill). True “already absent” only when probe returns `$null`.
- Start/Update free-port: probe catch → refuse (`EXIT_START_STALE_IDENTITY_UNVERIFIED` / `EXIT_PROCESS_PROBE_UNKNOWN`).

### INVALID ≠ ABSENT

- `Get-Hf3LaunchMetaState` triad: `ABSENT` (missing path) / `VALID` (parseable JSON) / `INVALID` (empty, parse error, null JSON, IO error).
- Start / Update / Stop each hard-fail on `INVALID` with dedicated exits; Stop’s “nothing to stop” is gated on `ABSENT` only.

### Listener Python process name

- `Test-LiveMatchesLaunchMeta` requires `Test-IsPythonProcessName`.
- `Stop-VerifiedHf3Identity` **listener** branch requires Python name before cmdline proof / `Stop-Process`.
- DIRECT ownership path in `Resolve-Hf3ListenerOwnership` also requires Python name (quality_guard gated).

### No real kill in tests

- V4 unit tests: source contracts only; explicitly “no OS side effects”.
- V4 injected runtime harness: replaces `Stop-Process` / `Start-Process` / CIM / TCP; asserts `__StopCalls.Count -eq 0` on negatives; PID `4242` used only as mapped/absent probe id (never `Stop-VerifiedHf3Identity -TargetPid 4242` against a real OS process).
- Legacy `p02_usb_hf3_pid_safety_runtime_tests.ps1`: still mocks `Stop-Process`; quality_guard forbids qualified real `Stop-Process` and literal `-TargetPid 4242` kill boundary.
- Unit `test_no_fake_pid_4242_real_kill_in_harness` still locks the V3 harness.

### Spaces in `--app-dir` quoting

- `Format-Hf3QuotedArg` + `Format-Hf3UvicornProcessArguments` build a single argv string; Start uses the formatter (not raw unquoted concatenation).
- Python mirror `format_uvicorn_process_arguments` quotes backends containing spaces; unit + quality_guard assert the quoted token.

---

## quality_guard V4 gates

`python3 quality_guard/check.py --root . --strict` → **PASS**, `issue_count: 0`.

Relevant strict codes now enforced when missing:

- `HF3_START_MISSING_INVALID_META_EXIT`
- `HF3_STOP_MISSING_INVALID_META_EXIT`
- `HF3_UPDATE_MISSING_INVALID_META_EXIT`
- `HF3_UPDATE_FREE_PORT_MISSING_LISTENER_CHECK`
- `HF3_PROCESS_PROBE_SILENT_ABSENCE` / `HF3_TCP_PROBE_SILENT_FREE_PORT`
- `HF3_LAUNCH_META_STATE_HELPER_MISSING`
- `HF3_UVICORN_ARGV_QUOTING_HELPER_MISSING`
- `HF3_LIVE_MATCH_MISSING_PYTHON_NAME`

`quality_guard.tests.test_hf3_safety`: **13 OK**, including `test_v4_invalid_meta_and_unknown_probes_fail_closed` and `test_v4_appdir_spaces_quoted_in_formatter`.

V4 behavioral unit file: **12/12 PASS** (manual loader; pytest not installed in this environment).

---

## Adversarial residuals (non-HOLD for code-only)

1. **`VALID` = JSON-parseable, not schema-complete.** Schema incompleteness is fail-closed on Stop (`EXIT_STOP_BLOCKED`) and on live-match/kill paths; free-port Start may archive/clear parseable meta only after PID identities are proven absent. Do not conflate with F-01 (malformed / unparseable).
2. **Preflight** still uses `Get-NetTCPConnection … -ErrorAction SilentlyContinue` for a **WARN-only** free/busy log. Not an authorization path for Start/Stop/Update kill or source swap. Out of F-05 scope (helper is fail-closed).
3. **TCP empty-listener heuristic** (`No MSFT_NetTCPConnection|ObjectNotFound|No matching|cannot find`) could theoretically misclassify an unusual provider error as free; residual to validate on Windows PS 5.1.
4. **quality_guard** kill-boundary scan targets `p02_usb_hf3_pid_safety_runtime_tests.ps1` only; V4 harness is separately mocked and unit-covered but not yet named in `check.py` rglob kill rules beyond generic `$PID` scan.
5. **Occupied-port Update** uses `Read-Hf3LaunchMeta` (throws `EXIT_INVALID_LAUNCH_META`) rather than the Update-specific exit code — still refuse/fail-closed, naming inconsistency only.
6. Working-tree V4 files were **uncommitted** at review time relative to tip `8dc2dfe`; packaging/CI tip evidence must be regenerated after commit.

---

## Physical gates — **BLOCKED**

| Gate | Status | Why |
|------|--------|-----|
| Windows PS 5.1 `p02_usb_hf3_v4_fail_closed_runtime_tests.ps1` | **BLOCKED** | No `pwsh`/`powershell` in this Linux agent; injected CIM/TCP/filesystem behavior unrun on host |
| Windows PS 5.1 `p02_usb_hf3_pid_safety_runtime_tests.ps1` | **BLOCKED** | Same |
| Real CIM/`Get-NetTCPConnection` UNKNOWN vs ABSENT on owner OS | **BLOCKED** | Mocked providers only |
| Owner Start / Stop / Update on 127.0.0.1:18878 | **BLOCKED** | SECURITY_SENSITIVE + WINDOWS_HOST; custody: mocked only; no owner runtime |
| Ports 18876/18877, cameras, owner DataDir | **BLOCKED** | Must remain untouched by any V4 proof |
| GitHub Actions windows-contract / tip SUCCESS for V4 commit | **BLOCKED / UNRUN** | Tip Actions cited in custody predate this uncommitted corrective |
| CreateProcess argv proof for `--app-dir` with spaces | **BLOCKED** | Formatter + Python mirror green; OS argv surface not executed here |

---

## Evidence executed this review

| Check | Result |
|-------|--------|
| Stay on `cursor/p02-usb-hf3-dshow-com-enum-83a8`; no other checkout; no push | Observed |
| Manual run of `test_p02_usb_hf3_v4_fail_closed.py` (12 tests) | PASS |
| `quality_guard/check.py --strict` | PASS (0 codes) |
| `unittest quality_guard.tests.test_hf3_safety` | 13 OK |
| Source invariant re-probe F-01..F-06 | all true |
| Windows runtime / owner lab | **not run** |

---

## Rollback note

If V4 working-tree changes must be abandoned: restore candidate script + quality_guard from tip `8dc2dfe` (expect V4 RED baselines again). Do not Start/Stop on the owner machine as part of rollback.
