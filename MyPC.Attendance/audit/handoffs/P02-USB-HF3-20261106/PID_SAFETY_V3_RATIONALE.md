# HF3 PID Safety V3 — technical rationale (English)

## Why V3

Independent audit of V2 COMPLETE (`58017ee3…` / freeze `0ea4264`) found:

1. Default Windows runtime harness could call real `Stop-Process` for hardcoded PID 4242.
2. Synthetic lab could PASS unconditionally / orphan a blocked `handle_request` child.
3. `--app-dir` ownership used cmdline substring (`IndexOf`), so a foreign app-dir plus HF3 path in another arg falsely matched.
4. Stop with no listener ignored failed launcher stop (`[void]`) and claimed OK when the port was free.

## Fixes

- Runtime harness: inject process map + **mocked `Stop-Process`** that never delegates to the real cmdlet; adversarial check that the live PowerShell `$PID` is never signaled; synthetic lab opt-in with request + finally teardown + port-free assert.
- `Test-Hf3UvicornCommandLine` / `uvicorn_cmdline_matches`: Windows argv split; exact `--app-dir` / `--port` / `--host` / `-m uvicorn` / `app.main:app` tokens; no substring fallback.
- Stop no-listener: tri-state launcher cleanup (absent / stopped / incomplete); fail closed + preserve meta.
- Start failure: preserve redacted attempt meta when cleanup blocked (ambiguous/foreign/incomplete).
- Update: refuse source swap if port free but prior launcher still live/unverifiable.

COM / VT_BSTR / CoInit / identity / physical gates unchanged and remain BLOCKED.
Owner must not run Start/Stop/runtime harness until independent review of this artifact.
