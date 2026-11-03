# PR12 Outbox Commit-Proof — Crash Fault Injection Matrix

| ID | Fault | Expected | Result |
|----|-------|----------|--------|
| C01 | kill_before_sql_commit (REMOVE) | No outbox row; live credential bytes survive; recover no-op | PASS (SQLite) |
| C02 | kill_before_sql_commit (REPLACE) | Staged discarded; live password unchanged | PASS (SQLite) |
| C03 | kill_after_sql_commit | Pending outbox row exists; recover promotes; live matches new password | PASS (SQLite) |
| C04 | kill_after_promote_before_ack | PROCESSING + live already new; recover idempotent DONE via payload SHA | PASS (SQLite) |
| C05 | disk_or_acl_error | Intent stays pending; retry/recover completes; SQLite+bytes consistent | PASS (SQLite) |
| C06 | stale_replay | Older generation abandoned; live equals newest committed credential | PASS (SQLite) |
| C07 | concurrent_REPLACE_REMOVE | Max generation wins; FS matches DB secret_ref for that generation | PASS (SQLite) |
| C08 | restart_and_retry | Exhausted FAILED not spun forever; SETTINGS_APPLY force_retry succeeds | PASS (SQLite) |
| C09 | postcommit_cleanup_failure | Outbox still applied; intent not discarded | PASS (SQLite) |
| C10 | legacy JSON journal | Pre-commit JSON never deletes referenced live secret | PASS (SQLite) |
| A01 | POST .../secret-fs-outbox/retry without SETTINGS_APPLY | 403 | PASS |
| A02 | GET /system/diagnostics unauthenticated | pending_count only; no paths/errors | PASS |

Physical Windows/camera gates remain **BLOCKED**. Do not run destructive credential ops on owner live DataDir.
