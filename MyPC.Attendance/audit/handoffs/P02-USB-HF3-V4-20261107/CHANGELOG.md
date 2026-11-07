# HF3 PID Safety V4 — fail-closed corrective

## Root causes (baseline tip `8dc2dfe`)

1. `Read-Hf3LaunchMeta` collapsed ABSENT and INVALID (malformed JSON) to `$null`.
2. Update free-port ignored INVALID meta and did not probe `listener_pid`/`listener_creation`.
3. Stop treated unreadable meta as “nothing to stop”.
4. `Get-Win32ProcessById` / `Get-Hf3PortListenerOwnerPids` used `-ErrorAction SilentlyContinue`, making UNKNOWN look like ABSENT/free.
5. Listener termination / live-match lacked Python process-name proof.
6. `Start-Process -ArgumentList` array join unsafe for `--app-dir` paths with spaces.

## Fixes

- `Get-Hf3LaunchMetaState` → ABSENT/VALID/INVALID; INVALID fails closed on Start/Stop/Update.
- Process/TCP probes throw `EXIT_PROCESS_PROBE_UNKNOWN` / `EXIT_TCP_PROBE_UNKNOWN` (no silent absence).
- Update free-port probes launcher **and** listener; `EXIT_UPDATE_STALE_LISTENER`.
- Listener kill + `Test-LiveMatchesLaunchMeta` require `Test-IsPythonProcessName`.
- `Format-Hf3UvicornProcessArguments` quotes paths with spaces; Start uses single argv string.
- Injected V4 behavioral harness + Guard/Pester/pytest contracts; no owner runtime.
