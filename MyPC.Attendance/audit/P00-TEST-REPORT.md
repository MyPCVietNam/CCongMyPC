# P00 TEST REPORT — MyPC Attendance v1.5

| Field | Value |
|-------|-------|
| Phase | P00 |
| Spec | v1.5 |
| Platform | Linux 6.12 (cloud agent), Python 3.12.3 |
| Command | `pytest tests/unit tests/integration -v --tb=short` |
| Timestamp (UTC) | 2026-11-01 (run during agent session) |
| Timestamp (Asia/Ho_Chi_Minh) | 2026-11-02 ~01:18 ICT |
| Result | **46 passed**, 1 pydantic warning (non-fatal) |

## Gate status

| Gate | Status | Evidence |
|------|--------|----------|
| UNIT_PASS | **PASS** | Morning, afternoon v1.5, overtime domain tests |
| MOCK_INTEGRATION_PASS | **PASS** | Auth, employees, mock camera, PM ingest, settings ACK, leave 403 |
| CAMERA_LAB_PASS | **BLOCKED** | No live EZVIZ RTSP/ONVIF decode in this environment |
| WINDOWS_INSTALL_PASS | **BLOCKED** | No Windows/NSIS host; installer not built |
| FACE_PILOT_PASS | **BLOCKED** | Models not downloaded; enrollment is P01 |
| EXIT_VERIFICATION_PASS | **BLOCKED** | `EXIT_VERIFICATION_GATE=BLOCKED` by design |
| PHYSICAL_OPERATION_PASS | **BLOCKED** | Requires on-site pilot |

## v1.5 critical assertions exercised

- PM window includes 23:55:59.999, excludes 23:56:00
- Nearest-to-18:00 + earlier tie-break + earlier-fallback + late-fallback
- No fabricated 18:00 observation (PM08)
- Settings reject afternoon end `19:00:00`
- Diagnostics expose `end_exclusive=23:56:00`

## Artifacts

See `release/SHA256SUMS-P00-20261101.txt` (UTC date stamp on filename).
