# Owner release acceptance checklist

1. Confirm active branch, exact base SHA/HEAD, source root (`MyPC.Attendance/`), whether `main` actually contains project source. No merge against stale PR tip.
2. Verify changed and removed paths, API/data/process/privacy impact map and rollback. Require independent security reviewer distinct from coding agent.
3. Baseline RED and feature GREEN with full command/exit logs; all required `guard-contract`, `backend-linux`, `frontend`, `windows-contract` checks green for same SHA. A skipped required check means HOLD.
4. Confirm Windows tests used PowerShell 5.1, did not run actual candidate `-Mode Start`, and did not call real `Stop-Process` against a fake PID.
5. Verify camera/COM strict identity, no name/index-only trust, COM `Release` and `VT_BSTR` tested, model pins retained; do not interpret `MODEL_PINS_PASS` as frame captured.
6. Validate FULL/CHANGED/EVIDENCE/COMPLETE ZIP with `python quality_guard/scripts/verify_handoff.py COMPLETE.zip`; SHA and paths; produce separate change manifest and external-safe redacted evidence.
7. Windows owner lab starts only after explicit human approval; preserve 18876/18877 and all existing DataDirs/HMAC. Capture actual UGREEN frame/resolution, unplug/replug, two-tab lease test, 30-min soak, signed USB CAMERA_LAB if evidence passes.
8. Production remains BLOCKED until installer, face pilot and security gates are separately signed. No secrets, raw biometric samples, PnP serial or unrestricted logs in the ZIP.
