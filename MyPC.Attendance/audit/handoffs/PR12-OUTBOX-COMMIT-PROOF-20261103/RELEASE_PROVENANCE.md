# Release provenance — PR12 outbox commit-proof

| Field | Value |
|-------|-------|
| Repository | https://github.com/MyPCVietNam/CCongMyPC |
| PR stack | base `cursor/pr11-realcam-ux-harden-83a8` @ `b74b59466a921ac54866eadeb5ec331649067e5b` |
| Feature commit | `6503713e683ee0d31a8c7d37a50a636139b47bf4` |
| Baseline (exact PR #12 head before this fix) | `b74b59466a921ac54866eadeb5ec331649067e5b` |
| Do not merge | `main` |

## What changed
- SQLite `secret_fs_outbox` + `camera_devices.secret_generation` (Alembic `20261103_0011`)
- Intents inserted in same transaction as camera credential updates
- Recover/replay only committed rows; generation/idempotency; flock + RLock
- `get_db`: commit then apply; postcommit cleanup cannot abort outbox
- Retry: `SETTINGS_APPLY` + CSRF; diagnostics redacted

## Not claimed
Physical CAMERA_LAB / FACE_PILOT / EXIT / INSTALLER PASS.
