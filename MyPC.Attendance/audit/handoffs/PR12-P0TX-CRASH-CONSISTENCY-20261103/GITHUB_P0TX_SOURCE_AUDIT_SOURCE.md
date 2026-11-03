# MyPC Attendance PR #12 P0 TX: direct GitHub source audit (2026-11-03)

Repository: `MyPCVietNam/CCongMyPC`  
PR: https://github.com/MyPCVietNam/CCongMyPC/pull/12  
Verified actual GitHub HEAD: `a702bc5de2eb0231ca4a9abdd8a1bcc3cdf26615`  
Feature commit: `52b2683caaf0910431f3989b5958c952cbe1f876`  

## Source-confirmed improvements

- `app/api/deps.py`, `app/services/secret_fs_outbox.py`: per-session `db.info` outbox; unrelated session B can no longer drain A's deletion list.
- `app/services/camera_credential_service.py`, `app/services/secrets_store.py`: REPLACE writes a unique encrypted staged file; canonical `camera-N.bin` is promoted with `os.replace` only after SQL commit. REMOVE and hard-delete queue post-commit cleanup. Rollback path discards staged refs.
- Added integration/unit tests for normal replace, rollback, remove, hard-delete, and independent outboxes. Existing evidence report shows `304 passed` and `npm audit` zero vulnerabilities. Independent test rerun was not possible here.
- Camera runtime badges/overview distinguish healthy LIVE decoder from merely configured MOCK/LIVE. Decoder stop ownership and biometric-frame deduplication have targeted changes.

## Confirmed release provenance discrepancy

Actual PR HEAD is `a702bc5de2eb0231ca4a9abdd8a1bcc3cdf26615`. However, the delivered `FINAL_HEAD.txt` says `894669a69952ca9d7f9de4d348d90635a67bb6ee`, while `ACCEPTANCE_MATRIX.md` says `3e820a55b3c7948c14fc8fc86f981e3a12bf25d1`. Handoff text/metadata must distinguish a fixed feature/source commit from the actual GitHub HEAD. A file tracked *inside the same Git commit* cannot reliably contain its own final commit SHA (editing it changes that SHA). Publish the final HEAD externally after push (CI/release notes), or label in-repo values `feature_commit` / `baseline_commit`. Source diff between feature commit and current HEAD contains only handoff/report/archive files, no application source changes.

## Remaining source-level failure modes (not independently reproduced on owner Windows)

1. **DB commit -> process crash before post-commit FS promotion**. In `get_db()`, `db.commit()` precedes `apply_outbox_after_commit()`. The queue is in `db.info`, not durable; a process kill between these operations can leave the DB committed while the live credential is old or missing (new camera). The staged encrypted blob may exist, but the shown outbox does not persist a replay record across restart.
2. **Post-commit I/O error is swallowed**. `apply_outbox_after_commit` catches errors, logs them, pops the outbox, returns a `failures` list that `get_db` does not inspect. A DB change may be returned as success with credential promote/remove not completed and no retry. This is not crash-consistent/retriable yet.
3. **Concurrent REPLACE on the same camera**. Per-session isolation solves cross-request queue drainage but does not serialize same-camera commit+promote. A commits; B commits and promotes; A promotes later -> DB reflects B while canonical credential reflects A. Requires versioned credential references, compare-and-swap, per-camera serialization or equivalent guarantees.
4. **Runtime binding before commit**. `/cameras/gateway/live/configure` starts a new RTSP gateway and changes in-memory registry before the SQL transaction is committed. If commit later fails, the process could retain a runtime configuration that DB did not save. Test rollback consistency for configuration and credential changes.

These are focused crash/concurrency concerns, not proof of data loss in existing user files. They should be tested on disposable staging data before live credential changes or hard-deletes.

## ZIP verification limitation and reported metadata

GitHub's connected text-content endpoint rejects binary ZIP blobs; this session could enumerate the GitHub objects, but could not download and independently hash/decompress their actual bytes. GitHub reported sizes: changed ZIP 1,513,921 bytes; full ZIP 3,348,847 bytes. The GitHub `SHA256SUMS.txt` *claims*:
- Changed ZIP: `97fa87f8f541e608c4cb410e5334b365b03841ebbd1b66fb452b9e4c4ff5dbfc`
- Full ZIP: `21122ae06e1f78d85dac760ff629d459807b7fdd783bfa3a2b906a0af137b8cd`

Use included `Verify-MyPC-PR12-GitHubZips.ps1` on Windows or supply the two downloaded ZIPs to complete independent byte-level validation. Do not claim actual SHA PASS until tested.

## Recommended disposition

**CONDITIONAL HOLD** for modifications to the owner's existing production DataDir, especially camera-credential REPLACE/REMOVE and hard-delete. Read-only UI/preview tests can proceed on an isolated staging copy. Ask Cursor to correct handoff commit metadata and explicitly test/handle post-commit crash/retry and same-camera concurrent writes. Preserve all biometrics, old camera secrets, SQLite data and earlier ACL fixes. Physical CAMERA_LAB/FACE_PILOT/EXIT_VERIFICATION/INSTALLER remain BLOCKED until owner evidence.
