# Independent review notes — HF3 V4.2 (agent self-check; not a substitute for ChatGPT reaudit)

## Baseline RED (V4.1 feature `979349f`)

Independent canaries (`independent_v41_residual_canaries.py`) reported **6 FAIL**:

| ID | Finding |
|----|---------|
| R9 | Prepare removed/replaced src without TCP+meta gates first |
| R9b | ModelsSourceDir checked after destructive path |
| R10 | Update ignored uvicorn.pid when launch meta VALID |
| R10b | Start ignored uvicorn.pid when launch meta VALID |
| R11 | Python DIRECT accepted blank listener name |
| R12 | Harness used synthetic Invoke-Hf3*Handler facades |

## Corrective deltas reviewed

1. Prepare authorization + stage/promote (`Invoke-Hf3PrepareHandler`, no live `Remove-Item -Recurse $srcDir`).
2. `Test-Hf3PidRecord` in Start/Update/Stop free-port and handler paths.
3. `is_python_process` required for DIRECT.
4. Harness extracts production handlers + `Extract-ModeText`; asserts zero Stop-Process on negatives.

## Residual limitations (honest)

- Windows PowerShell 5.1 behavioral harness runs in GitHub Actions Windows job; Linux agent used `pwsh` Core for preflight with mocked CIM/TCP only.
- No owner host, no real listener, no physical USB camera evidence in this package.
- `Format-Hf3CreationStamp` added so JSON DateTime promotion cannot false-mismatch live creation compares.

## Verdict of this note

Code-path corrective appears to address R9–R12 canaries (GREEN on working tree). Final gate remains **READY_FOR_INDEPENDENT_REAUDIT** after Actions 4/4 on immutable feature SHA and COMPLETE remote SHA verify.
