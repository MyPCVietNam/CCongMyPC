# P00 CHANGELOG — MyPC Attendance v1.5

## Added

- Repository scaffold under `MyPC.Attendance/` with backend, frontend, gateway template, models manifest, docs, tests, tools.
- FastAPI core: health, diagnostics, auth (Argon2id + signed cookie + CSRF), employees CRUD, cameras + mock diagnostics/preview/ROI, attendance daily/timeline/afternoon-reference + mock observation ingest, settings draft/apply/history with ACK protocol, leave submit + TIMEKEEPER_APPROVE gate, overview.
- Domain rules engine: morning AM01–AM11 semantics; **afternoon [17:00, 23:56)** with 18:00 nearest/earlier-fallback selection (v1.5); leave expectations; overtime state machine basics.
- SQLite schema (WAL, FK, busy_timeout) for employees, users, cameras, regions, observations, attendance events, leave, config revisions, audit logs.
- Vietnamese React+Vite UI shell: all required nav screens, mock indicator, footer MyPC Việt Nam → https://mypc.vn, settings showing 17:00–23:55 window.
- License inventory: `docs/THIRD_PARTY_NOTICES.md`, `docs/licenses.lock.json`, ADRs, assumptions.
- Mock camera synthetic PNG frames without OpenCV dependency.
- Unit + integration tests (46) covering v1.5 PM selection and P00 API gates.

## Corrected vs older drafts

- Afternoon recognition end is **23:55 end-of-minute** (`23:56:00` exclusive), not 19:00.
- Settings apply rejects `19:00:00` afternoon end.
- 18:00 is selection anchor only; never fabricated observation timestamp.

## Known issues / blockers

- `CAMERA_LAB_PASS`: BLOCKED (no live EZVIZ RTSP verification in this environment).
- `EXIT_VERIFICATION_GATE`: BLOCKED by design until physical calibration.
- Windows installer / WinSW: BLOCKED (Linux agent; no fake EXE).
- YuNet/SFace weights: listed, not downloaded (`PENDING_DOWNLOAD_VERIFY`).
- FFmpeg packaging: LICENSE_BLOCKED pending audited binary.
- Face enrollment UI/API: deferred to P01.
- Full overtime persistence/UI cards: P04.
- XLSX/PDF monthly reports: P05.
