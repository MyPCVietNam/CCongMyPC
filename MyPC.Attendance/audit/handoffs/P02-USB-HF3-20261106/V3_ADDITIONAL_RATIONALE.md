# PID Safety V3 additional corrective (independent 6 RED → GREEN)

## Defects on tip / freeze `00858e3` / feature `97c1e9`

1. Start free-port path deleted `uvicorn.pid` / `uvicorn.launch.json` without probing live launcher.
2. `uvicorn_cmdline_matches` / PS mirror accepted `python -c … -m uvicorn …`.
3. DIRECT listener lacked Python process-name check in PS.
4. Opt-in synthetic lab used qualified real `Stop-Process` by port owner alone.

## Fixes

- Start: `Read-Hf3LaunchMeta` + `Get-Win32ProcessById`; `EXIT_START_STALE_LAUNCHER` / `EXIT_START_STALE_IDENTITY_UNVERIFIED` / legacy PID block; archive then clear only when proven absent.
- Entrypoint: contiguous `python → -m uvicorn app.main:app`; reject `-c`/`--reload`/`--workers`.
- DIRECT: `Test-IsPythonProcessName $listener.Name` before accept.
- Synthetic lab: approval env; temp `.py` file; natural exit; no qualified real Stop-Process.
- Quality Guard: extended `check.py` + `test_hf3_safety` gates; CI fetch-depth 0; rename `$profile` in Inspect-LocalRuntime.ps1.

Physical gates remain BLOCKED. HOLD on owner Start/Stop/runtime until independent audit of next COMPLETE.
