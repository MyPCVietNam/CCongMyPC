# Cursor Task - PR #12 Targeted Transactional Integrity Corrections

Repository: https://github.com/MyPCVietNam/CCongMyPC
PR: #12 (open, do not merge to main)
Feature code base: `db571d995714dfbda3ce006f900f9ecb34a315c7`
PR HEAD confirmed: `0d655673a3cd600e6041f1ae70de08c2cc0aa3d1`

Read `AUDIT_REPORT.md` completely. This is NOT a new broad feature phase or UX redesign. Preserve the PR #12 camera/UX/security functionality already implemented.

**P0-A: Eliminate process-shared camera-secret deletion queue.** Current `AppState.pending_camera_secret_deletes` is shared by all request handlers and drained by any `get_db()` commit. The attached `REPRODUCTION.txt` demonstrates that request B can delete request A's credential before A commits and then A rolls back. Use a per-request/session transaction-owned outbox, not a global list. Never let unrelated commits/rollbacks drain or discard each other's work. Ensure post-commit failures are observable and retriable. Include deterministic interleaving tests.

**P0-B: Make camera credential CREATE, REPLACE, REMOVE fully rollback-safe.** `apply_camera_credentials()` writes or removes `camera-{id}.bin` during `create_camera` and `update_camera` before SQL commit. Stage new encrypted versions under unique refs, finalize only after the owning DB commit, and protect pre-existing credentials if the DB fails. Do not overwrite a live encrypted file before commit. Cover SQL flush failure, SQL commit failure, deferred file-cleanup failure, concurrency, restart, and crash recovery with tests.

**P1: Review and correct source-level regressions.**
- Honest fleet/selected-camera status: `overview.py` uses existence of any MOCK camera and `health.py` picks first provenance regardless of decoder readiness.
- Distinguish generic read/corruption events from actual HEVC reference errors; real camera A/B required, not Linux-only simulated PASS.
- Decoder `stop()` must not permit a second reader while a blocked first reader still exists.
- Biometric frame ID deduplication must be atomic and backed by durable idempotency for real attendance side effects.
- Keep camera-backed evidence and history read-only safe while archiving/deleting profiles.
- Ensure Python supported versions match actual imports (`imghdr` removed from Python 3.13).
- Fix the narrow mobile Camera selector filter row where the filter label is partly covered by the dropdown; preserve readability and large touch targets.

**Packaging evidence must be corrected.** The user-provided changed ZIP SHA256 is `f7e97dec02ac9a3a810b8c396b27d6a5eaae046e8f7e08822abbd2b339410368`, full ZIP SHA256 is `da3c97894b87a5c45e80602bb81884551b89ad66f7c5a2ed0f0d339ddcb56fe6`. Embedded manifest claims different hashes, and `FINAL_HEAD.txt` contains an unresolvable SHA `c8d50e9d0b8423ce9d96f926c9503e5dce39b7e8`. Produce manifest outside the final archives, after freezing archive bytes, and verify pushed HEAD SHA and files.

**Business rule checkpoint**: current v1.5 code explicitly uses afternoon `[17:00,23:56)`, photo 17:55-18:00, reference 18:00. Do NOT silently replace it with an earlier policy. Document the operator decision point and preserve approved rules until the owner signs off.

**Verification**: full pytest, targeted concurrency/fault-injection tests, frontend build, npm audit, static policy and Windows PowerShell 5.1 compatibility, model provisioning diagnostics. Report results with exact final git HEAD. Keep physical CAMERA_LAB/FACE_PILOT/EXIT_VERIFICATION/INSTALLER BLOCKED until real owner evidence.

**Deliver**: a NEW changed-source audit ZIP and separately a NEW full-source ZIP with manifest, hashes and test reports; Vietnamese Windows staging/upgrade instructions including full stopped-DataDir backup and disposable restore. Do not merge main, and do not claim Windows physical pass from Linux tests.
