# Independent adversarial review — Quality Guard + HF3 PID safety (V3-ADD)

Reviewer: separate agent (read-only code review; no production edits).  
Tip reviewed: `cursor/p02-usb-hf3-dshow-com-enum-83a8` (`b4652d497bc7cceb53d510ab70bdccd50db2724a`).  
Scope: listed HF3 ownership/kill helpers + Quality Guard static/unit contracts only.

## 1) Verdict (code-only gates)

**PASS**

- `python3 quality_guard/check.py --root . --strict` → `PASS`, `issue_count: 0`
- `python3 -m unittest quality_guard.tests.test_hf3_safety -v` → 11/11 OK
- Adversarial ownership/kill cases below are closed in production PS + mirrored helper + guards

This is a **code-only** verdict. It does **not** authorize USB/camera/physical PASS, owner HF3 Start, or soak.

## 2) Positive protections found

| Adversarial case | Protection |
|------------------|------------|
| `python -c` spoof with trailing uvicorn tokens | Contiguous interpreter walk requires `[safeFlags*] -m uvicorn app.main:app`; any `-c` / `-c*` token fails closed (`Test-Hf3UvicornCommandLine` ~L217–241; `uvicorn_cmdline_matches` / `_uvicorn_module_entrypoint_index`) |
| Free TCP port but live prior launcher | Start free-port branch probes `uvicorn.launch.json`, refuses with `EXIT_START_STALE_LAUNCHER` / `EXIT_START_STALE_IDENTITY_UNVERIFIED`, **no kill** (~L805–834) |
| Fake PID `4242` reaching real `Stop-Process` | Runtime harness uses `$synthListenerPid` + **mocked** `Stop-Process` only; static guards ban literal `-TargetPid 4242`, line-start `Stop-Process`, and qualified `Microsoft.PowerShell.Management\Stop-Process` |
| `--app-dir` substring / foreign path in `--log-config` | Exact canonical `--app-dir` equality only; no `IndexOf($backendNorm)` (PS ~L253–254; Python helper; guard + unit/Pester contracts) |
| DIRECT listener without Python process name | `Resolve-Hf3ListenerOwnership` requires `Test-IsPythonProcessName $listener.Name` before `DIRECT` (~L331–340); guard asserts presence |
| Synthetic lab kill-by-port | Opt-in + `MYPC_HF3_SYNTHETIC_LAB_APPROVED=1`; never HF3 ports; natural exit only; lingering process → FAIL and **refusing kill** (~L290–294) |
| Blank creation | `Stop-VerifiedHf3Identity` refuses missing `ExpectedCreation` (~L448–450); schema/meta match fail closed; unit asserts blank creation ≠ match |
| PID reuse | Kill/live-match require PID **and** creation equality; Start free-port creation mismatch → `EXIT_START_STALE_IDENTITY_UNVERIFIED`; conhost never killed |
| Health spoof | Start PASS needs top-level `status=ok` + `startup_phase=READY` only; nested ok/READY rejected |
| Legacy PID-only Stop | `EXIT_STOP_BLOCKED_LEGACY_PID` — no terminate by numeric PID alone |

## 3) Remaining defects / residuals

No **code-only gate blockers** found in the reviewed production kill/ownership path.

Non-blocking residuals (do **not** soften assertions to “fix” them):

1. **`hf3_pid_ownership.py:286–291`** — Python mirror allows `DIRECT` when `listener.name` is empty (mock convenience). Production PS rejects non-Python names. Keep PS/guard assertions strict; do not weaken them to match the empty-name mirror.
2. **Windows PS 5.1 runtime / Pester** — not executed on this Linux reviewer host; treat `windows-contract` as evidence from CI, not from this review session.
3. **Prior review note obsolete** — optional synthetic lab no longer performs qualified real `Stop-Process`; current lab fails closed without kill.

## 4) Physical gates

**Must stay BLOCKED:**

- `USB_WINDOWS_PHYSICAL`
- `USB_STABILITY_30_MIN`
- `USB_CAMERA_LAB_OWNER_SIGN`
- Face pilot / installer / production-ready claims tied to physical evidence

Source/CI green ≠ camera frame, soak, or owner USB lab sign-off. `PACKAGE_META.json` remains `owner_usb_physical_approved: false`.

## 5) Assertion / Start posture

- Do **not** soften Quality Guard or HF3 safety assertions.
- Do **not** treat this review as permission to run owner **Start** on HF3/`18878`, touch `18876`/`18877`, DataDir, HMAC, or USB hardware.
- Cleanup/Stop remains identity-bound (PID + creation + role proof); free port never implies safe silent meta erase when a prior launcher is still live.
