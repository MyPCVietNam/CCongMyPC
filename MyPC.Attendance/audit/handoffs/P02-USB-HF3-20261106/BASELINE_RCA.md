# Baseline RCA — PID safety V3

## Input

- V2 COMPLETE SHA256 `58017ee3…` / freeze `0ea4264` / tip `a3b995e`
- Independent suite `test_hf3_pid_safety_v3_independent.py`: **6 RED** on V2 tip

## Defects

1. Runtime harness called real `Stop-Process` for synthetic PID 4242.
2. Synthetic lab unconditional PASS / blocked `handle_request` orphan risk.
3. Foreign `--app-dir` accepted via cmdline path substring.
4. Stop ignored failed launcher stop when port already free.

## Non-goals

No Prepare; no physical gate PASS; no owner Start/Stop until V3 audit.
