# PR13 Release Safety / Fresh-Install Corrective

Stacked on PR #13 (C11–C14). Does **not** merge to main. Does **not** touch production DataDir.

## Fixes

| ID | Severity | Summary |
|----|----------|---------|
| SECURITY-P0 | P0 | Quarantine contaminated public FULL ZIPs; allowlisted packaging + fail-closed scanner |
| INSTALL-P0 | P0 | Fresh empty DataDir → `create_all` + stamp HEAD `20261103_0012`; versioned DBs upgrade; unknown legacy fails closed |
| CLEANUP-P1 | P1 | `discard_on_rollback` registered before `db.flush` in `queue_promote` |
| COMPAT-P1 | P1 | FastAPI pin gate `>=0.115,<0.116`; version-resilient `FinalizingAPIRoute` for C13 503 |

## Tests

- `295 passed` on Python 3.12.3 + FastAPI 0.115.14 (see `reports/pytest-summary.txt`).
- Includes `tests/test_pr13_release_followups.py` and C13 pin/ASGI assertion.

## Artifacts

- Clean CHANGED/FULL ZIPs + external `SHA256SUMS.txt` (written after ZIP freeze).
- Contaminated historic FULL ZIPs quarantined — see `audit/QUARANTINE_PUBLIC_ARCHIVES/`.

## Gates

CAMERA_LAB / FACE_PILOT / EXIT_VERIFICATION / INSTALLER physical = **BLOCKED**.
