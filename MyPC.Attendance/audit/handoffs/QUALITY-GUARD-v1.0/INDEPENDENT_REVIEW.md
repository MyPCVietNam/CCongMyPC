# Independent adversarial review (Quality Guard + HF3 V3)

Reviewer: separate agent (diff-focused + adversarial recheck). Coding agent pytest counts are not sole evidence.

## Findings

| Item | Result |
|------|--------|
| Default harness: no literal `-TargetPid 4242`; mocked Stop-Process | PASS |
| Exact `--app-dir` (no IndexOf substring) | PASS |
| Foreign app-dir + HF3 in `--log-config` rejected | PASS |
| `quality_guard/check.py --strict` on tip | PASS (0 codes) |
| Physical gates BLOCKED in docs | PASS |
| Overlay bytecode `__pycache__` | FIXED (removed; gitignored) |

## Residual risks

- Opt-in `-RunSyntheticLab` may use module-qualified real Stop-Process only for verified synthetic-port owners.
- Windows PS 5.1 runtime not executed on this Linux agent (windows-contract job UNRUN until Actions runs).
- GitHub Actions workflows API showed 0 workflows before this push — treat CI as UNRUN until run links exist.

## Rollback

Restore prior tip `ab1161dd…` for HF3 scripts if needed; re-run `check.py --strict` and `test_hf3_safety`. Do not Start on owner machine as part of rollback.
