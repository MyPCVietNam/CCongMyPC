# Release provenance (no self-embedded tip SHA)

Git cannot store a commit's **own** SHA inside that same commit (editing the file changes the SHA).

| Field | Meaning | Where to read |
| --- | --- | --- |
| `feature_commit` | Immutable application fix for this handoff | `FEATURE_COMMIT.txt` in this folder |
| `baseline_commit` | Prior PR tip before this fix | `BASELINE_COMMIT.txt` |
| GitHub PR HEAD | Actual branch tip after push | **GitHub** `gh pr view 12 --json headRefOid` / compare API — not an in-tree self-hash |

ZIP `SHA256SUMS.txt` is written **after** archive bytes are frozen and lives **beside** the ZIPs (not inside them).
