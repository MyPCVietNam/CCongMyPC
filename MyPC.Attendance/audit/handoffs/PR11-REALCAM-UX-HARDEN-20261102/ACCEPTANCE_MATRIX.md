# Acceptance matrix — RealCam UX Harden (unified P0/P1)

**Baseline:** `cursor/pr11-realcam-reliability-83a8` @ `416bc2dcca4c6b117249aca02c5293a8e53ffeae`  
**Delivery branch:** `cursor/pr11-realcam-ux-harden-83a8`  
**Final HEAD:** `db571d995714dfbda3ce006f900f9ecb34a315c7` (feature) + delivery docs commit on push tip
**Timezone note:** owner times Asia/Bangkok (UTC+7).

Codes: `PASS` only with automated evidence at this HEAD; `BLOCKED` until owner Windows/camera evidence; never invent physical PASS.

| ID | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| P0-1 | Transaction-safe camera secret delete (after DB commit; rollback keeps credentials) | PASS | `tests/integration/test_camera_delete_transaction.py` |
| P0-2 | Biometric frame freshness — no good-frame reuse when DEGRADED/RECONNECTING/OFFLINE/STOPPED; uniqueness; integrity | PASS | `tests/unit/test_biometric_frame_freshness.py` + registry/gateway |
| P0-CAM | HEVC corrupt reject, FFmpeg open lock, clear `_latest_good` on degrade, reconnect telemetry | PASS (code+unit) | `gateway.py` `_FFMPEG_OPEN_LOCK`, `HEVC_REF_OR_CORRUPT`; physical R03–R08 BLOCKED |
| P1-NPM | npm advisories resolved without `--force` | PASS | vite 6.4.5, react-router-dom 7.18.5; `npm audit` → 0 vulns |
| P1-UX-NAV | Six-group operator nav + progressive disclosure | PASS | `Layout.tsx`; `test_operator_ux_nav_contract.py` |
| P1-UX-CAM | Camera: LIVE + Kết nối lại / Sửa / Kiểm tra; admin `<details>` | PASS | `CameraPage.tsx` + screenshots |
| P1-UX-LAB | Windows Lab guided wizard; JSON/HMAC in details | PASS | `WindowsLabPage.tsx` + screenshots |
| P1-UX-SET | Settings admin links (Lab / Logs) | PASS | `SettingsPage.tsx` |
| T-FULL | Full pytest at final HEAD | PASS | see `reports/pytest.txt` (295 passed) |
| T-FE | Frontend production build | PASS | vite build → `backend/app/static` |
| G-CAMERA_LAB | Physical CAMERA_LAB gate | BLOCKED | Needs owner LAN EZVIZ evidence |
| G-FACE_PILOT | FACE_PILOT gate | BLOCKED | Needs owner consented cases |
| G-EXIT | EXIT_VERIFICATION gate | BLOCKED | Needs owner evidence |
| G-INSTALLER | INSTALLER gate | BLOCKED | Needs owner Windows installer evidence |
| R03–R06 | H.265/H.264 · TCP/UDP · Wi-Fi/RJ45 A/B | BLOCKED | Plan in `AB_TEST_PLAN_VI.md` — one variable per run |
| D01–D03 | Changed ZIP, full ZIP, VI guide, SHA256 | PASS | this handoff folder |

## Counts (source verification at packaging)

- Automated PASS: see report footer
- FAIL: 0 (at packaging)
- BLOCKED physical gates: CAMERA_LAB, FACE_PILOT, EXIT_VERIFICATION, INSTALLER (+ R03–R06 A/B)

## Truthfulness rules

- LIVE decode ≠ CAMERA_LAB_PASS (HMAC)
- MOCK config ≠ LIVE runtime
- Degraded/corrupt frames never eligible for recognition
- No physical gate marked PASS without owner Windows evidence
