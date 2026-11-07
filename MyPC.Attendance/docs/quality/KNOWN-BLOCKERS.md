# Known blockers at Quality Guard v1.0 baseline

Evidence basis: uploaded FULL SOURCE from MyPC Attendance PR #27 PID Safety V2, packaging freeze `0ea4264440bf330f005af7447bbd6bdb6cfabb46`; COMPLETE SHA256 `58017ee3f09b5e6f21dd6097c390058ff48616cf83cc8b1932e93a32627a0e6a`.

1. `p02_usb_hf3_pid_safety_runtime_tests.ps1`: a synthetic object for PID 4242 flows into `Stop-VerifiedHf3Identity`, whose implementation can call live `Stop-Process`. The same test file has a live `Stop-Process` branch for synthetic lab cleanup. This is forbidden for a no-host-side-effects automated safety test. Refactor to a pure/mocked process adapter and owner-only separate lab.
2. `hf3_pid_ownership.py`: `uvicorn_cmdline_matches` treats backend path appearance anywhere in command text as proof, including `--log-config` with wrong `--app-dir`. `Test-Hf3UvicornCommandLine` in PowerShell similarly uses fallback substring `IndexOf($backendNorm)`. Replace with parsed/normalized exact `--app-dir` argument value, duplicate/ambiguous flags rejected.
3. Current Windows Pester/runtime integration results are not owner-proven; agent CI descriptions are not GitHub check runs.
4. Repository public `main` only contained `LICENSE` at audit time; the source and most history are in stacked feature branches. Do not protect a LICENSE-only branch and infer that the feature is tested.
5. HF3 `Diagnose` on owner machine previously passed mapping (`CAPTURE_MAPPING_VERIFIED=true`), but no verified real video frame/soak/USB CAMERA_LAB sign has been provided.

`quality_guard/check.py --strict` and the independent hostile tests intentionally BLOCK this baseline. Resolve code and tests, preserve source custody, then rerun. Never skip failing checks to unlock merge.
