# PR6 Follow-up Changelog (2026-11-02)

- Canonical UTC Zulu + `payload_json` HMAC for pilot approvals (SQLite-safe).
- Server-derived pins; AUTO_VALIDATED requires AB + CAMERA_LAB + FACE_PILOT evidence.
- REAL_CAMERA enrollment immutably bound to one LIVE camera/config/approval.
- ACTIVE gallery loaded for analyze-once / observe-shadow; honest A/B statuses.
- LIVE RTSP: IPv4 literal + destination pin; single secret write.
- Alembic `20261102_0006` enrollment binding columns + demote unsigned AUTO_VALIDATED.
- Windows Test-MyPCCamera.ps1 honesty extensions.
- New unit/integration tests; full suite 155 passed on Linux.
