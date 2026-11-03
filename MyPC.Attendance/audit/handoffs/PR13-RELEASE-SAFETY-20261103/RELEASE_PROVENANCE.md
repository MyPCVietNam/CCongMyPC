# Release provenance

| Field | Meaning | Value |
|-------|---------|-------|
| `feature_commit` | Application fix commit (bootstrap/packaging/C13) | see `FEATURE_COMMIT.txt` |
| `baseline_commit` | Audited PR13 tip before this corrective | see `BASELINE_COMMIT.txt` |
| `FINAL_HEAD` | GitHub PR tip after packaging push | see `FINAL_HEAD.txt` (set after push) |

`SHA256SUMS.txt` is written **after** ZIP bytes are frozen and lives **beside** the ZIPs (not inside them).
