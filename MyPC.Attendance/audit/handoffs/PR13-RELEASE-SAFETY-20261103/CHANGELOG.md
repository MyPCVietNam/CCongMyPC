# Changelog — PR13 release safety

- **SECURITY-P0:** Quarantine public FULL ZIPs that embedded `data/` / secrets; add allowlisted packager + recursive sensitive-path scanner; CI-oriented fail-closed checks.
- **INSTALL-P0:** `schema_bootstrap.bootstrap_schema` — fresh stamp HEAD vs upgrade vs unknown-legacy fail-closed; idempotent migrations 0009–0012.
- **CLEANUP-P1:** Register `discard_on_rollback` before `db.flush` in `queue_promote`; `_stage_replace` unwinds on promote failure.
- **COMPAT-P1:** FastAPI version gate on health/diagnostics; `FinalizingAPIRoute` so C13 503 works even if yield teardown timing changes.
- Preserve C01–C14 outbox/lifecycle behavior; no attendance policy or UX redesign.
