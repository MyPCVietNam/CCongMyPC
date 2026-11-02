# PR7 Corrective — Test Report

- **Date:** 2026-11-02 (owner zone Asia/Bangkok; machine UTC)
- **Branch:** `cursor/pr7-corrective-evidence-83a8` (from PR7 tip `81b9e94`)
- **Command:** `cd MyPC.Attendance && .venv/bin/pytest tests/ -q`
- **Result:** **167 passed**
- **Frontend:** `npm run build` — success
- **Alembic:** through `20261102_0007`
- **API smoke:** `audit/PR7-CORRECTIVE-BROWSER-SMOKE.json` — login, employee, overview (EXIT BLOCKED), MOCK preview, analyze-once `BLOCKED_GALLERY` / `AUTO_TEST_ONLY`, gateway health `camera_lab_pass=false`
- **Not equivalent:** P00 Cloud env 46 tests — discarded as validation of this code

Physical Windows/camera/installer cases: **BLOCKED / NOT_RUN**.
