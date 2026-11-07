# MyPC Engineering Quality Guard — repository protection, not production deployment

This directory contains purely static/pure checks, an offline ZIP validator and a Windows PowerShell 5.1 Pester contract. Never execute existing owner candidate scripts from CI.

From repository root:

```bash
python -m unittest discover -s quality_guard/tests -p 'test_*.py' -v
python quality_guard/check.py --root . --strict
node --test .cursor/hooks/guard-shell.test.cjs
```

`--strict` is **intentionally RED** against the PID Safety V2 baseline until the unsafe fake PID kill path and lax app-dir identity are removed. The failed CI is a safety control, not a problem to suppress.

The hook is a best-effort prevention layer for Cursor terminal commands only. A person can bypass it and some non-shell tools don't pass through it. GitHub required checks, least permissions, independent reviews and OS boundary injection remain mandatory.

The Windows job uses a GitHub-hosted Windows 2022 runner and `shell: powershell` (Windows PowerShell 5.1). It parses scripts and runs only pure Pester/static checks; no real owner data or camera will be available. Physical owner acceptance is separate.

The `verify_handoff.py` script checks manifest/hash/ZIP traversal and dangerous file suffixes. It cannot by itself determine whether a benign-looking text log contains a password; independent review of redacted evidence is still required.
