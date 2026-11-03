# Acceptance — PR #12 crash-consistency correction

**feature_commit:** `4eba3d67a53468a2240fd2373b07aa95aa0cd49a` (immutable app fix)  
**baseline_commit:** `a702bc5de2eb0231ca4a9abdd8a1bcc3cdf26615`  
**GitHub PR HEAD:** read from GitHub after push — see `RELEASE_PROVENANCE.md` (not self-embedded).

| ID | Item | Status |
| --- | --- | --- |
| P0-01/02 | Prior session outbox + staging (preserved) | PASS |
| Crash | Journal before commit; recover after kill | PASS |
| Post-commit FS fail | 503 SECRET_FS_OUTBOX_INCOMPLETE + retry API | PASS |
| Concurrent REPLACE | Per-camera lock serialize | PASS |
| LIVE rollback | Runtime compensate unbind | PASS |
| Provenance | feature/baseline files; no self-SHA tip | PASS |
| G-* physical | BLOCKED | BLOCKED |
