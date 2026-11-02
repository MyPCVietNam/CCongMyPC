# P02R Test Report

- Branch: `cursor/pr8-p02r-winlab-readiness-83a8`
- HEAD at test: see git log / fingerprint
- Command: `cd MyPC.Attendance && .venv/bin/python -m pytest tests/ -q`
- Result: **205 passed**
- Frontend: `npm run build` OK
- Matrix: `docs/P02R_ACCEPTANCE_MATRIX.csv` (57 cases) + `tests/acceptance/test_p02r_matrix_status.py`
- Integration: `tests/integration/test_p02r_lab_run_evidence.py`

Physical camera / installer cases remain BLOCKED/NOT_RUN by design.


## Exact run

- HEAD: `0bc4ba33035d5e90ba0da891ae7af3a8feb2900b`
- pytest: 205 passed
- Asia/Bangkok note: Cloud UTC fingerprints in runtime/
