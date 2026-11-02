# PR6 Follow-up — Test Report

- **Platform:** Linux cloud agent (UTC machine clock; owner zone Asia/Bangkok)
- **Command:** `cd MyPC.Attendance && .venv/bin/pytest tests/ -q`
- **Result:** **155 passed** (2026-11-02)
- **Frontend:** `npm run build` — success (Vite)
- **Alembic:** upgrade through `20261102_0006` exercised via `create_app`
- **SQLite reproducers:** `tools/repro_sqlite_timezone.py` and `tools/repro_sqlite_hmac_roundtrip.py` still demonstrate the *pre-fix* failure modes; application path covered by `tests/unit/test_pr6_followup_utc_hmac.py`

## New tests

- `tests/unit/test_pr6_followup_utc_hmac.py`
- `tests/unit/test_pr6_followup_paired_gallery.py`
- `tests/integration/test_pr6_followup_gates.py`

Physical Windows/camera cases remain BLOCKED/NOT_RUN — see matrix.
