# Changelog — PR13 C11–C14

## c2c7ba72e97a176789d30bb4b94171e618c38720
- C11: remove blind orphan scrub from runtime `recover_pending_outbox`; staged leases + exclusive age-gated maintenance scrub
- C12: `_next_generation` uses column SELECT (no full `db.refresh`) preserving dirty camera fields
- C13: worker-thread finalize + ASGI send-wrapper delivers HTTP 503 `SECRET_FS_OUTBOX_INCOMPLETE`
- C14: `lifecycle_id` / `camera_lifecycle_id` fence (Alembic `20261103_0012`)
- Tests: `tests/test_pr13_independent_regressions.py` (C11–C14)
