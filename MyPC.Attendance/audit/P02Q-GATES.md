# P02Q Gates

Allowed statuses only: PASS / FAIL / BLOCKED / NOT_RUN

| Gate | Status | Evidence |
|------|--------|----------|
| P02-HF-LIVE (unit/replay wiring) | **PASS** | Registry+preview+revision tests |
| P02-HF-SECURITY (URI/auth unit+integration) | **PASS** | RTSP policy + API 422/CSRF tests |
| P02Q-ORIGINAL (immutable + geometry) | **PASS** | Hash/readonly + YuNet inverse tests |
| P02Q-DIAGNOSTICS (API honesty) | **PASS** (synthetic) | Quality diagnostics UNVERIFIED/VENDOR_SPEC |
| P02Q-AUTO-SHADOW | **PASS** (default mode) | AUTO_TEST_ONLY enforced |
| P02Q-AUTO-APPROVAL | **BLOCKED** | No LIVE pilot / hard blockers in evaluator |
| P02Q-AB-REPLAY | **PASS** (synthetic only) | Evaluator + CSV; cannot enable AUTO |
| P02-ATTENDANCE regression | **PASS** | Included in 118 suite |
| P02Q-CAMERA-LIVE | **BLOCKED** | No physical camera |
| P02Q-WINDOWS | **BLOCKED** | No owner Windows lab run |
| P02-EXIT / person detector | **BLOCKED** | License/weights |
| P02-FACE-PILOT | **BLOCKED** | No live biometric pilot |
| INSTALLER | **NOT_RUN** | Not compiled on Windows |
| MERGE_MAIN | **NOT_RUN** | Requires explicit owner approval |

## Matrix

See `docs/ACCEPTANCE_TEST_MATRIX.csv` (54-case backlog). Many OWNER_WINDOWS_LIVE rows remain NOT_RUN/BLOCKED by design.
