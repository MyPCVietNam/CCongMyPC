# MyPC Attendance PR #12 - Independent Source Audit

Date: 2026-11-02. Scope: user-supplied changed-source and full-source archives, plus GitHub PR #12 ancestry verification. No production databases, passwords, employee biometric data or video were accessed.

## Decision

CONDITIONAL HOLD for migration using the owner's live DataDir. Two independently identified P0 transactional integrity gaps remain. UI layout can be tested on a disposable, separate test profile. Do NOT hard-delete camera profiles or replace/remove camera credentials on live DataDir until the P0 issues are fixed and tested.

## Source provenance and integrity

- Changed source: 37 ZIP entries; Full source: 405 ZIP entries.
- Both ZIPs pass `ZipFile.testzip()`.
- 37/37 changed-source files identically match files at equivalent paths in full-source archive.
- Uploaded changed ZIP SHA256: `f7e97dec02ac9a3a810b8c396b27d6a5eaae046e8f7e08822abbd2b339410368`.
- Uploaded full ZIP SHA256: `da3c97894b87a5c45e80602bb81884551b89ad66f7c5a2ed0f0d339ddcb56fe6`.
- Embedded SHA256SUMS claims different ZIP hashes: changed=`ecd0be75de70fc1b98e9881519612829832b9c1de61fcd876117f0adb50bae12`, full=`a6d61bafd02cd6ac450ec68982a8e040abe2f31866822d526ea57e680ecca1db`.
- All other 15 entries in the embedded SHA256SUMS match their corresponding files.
- Embedded FINAL_HEAD.txt refers to `c8d50e9d0b8423ce9d96f926c9503e5dce39b7e8` which GitHub does not resolve as a commit. GitHub PR #12 head is `0d655673a3cd600e6041f1ae70de08c2cc0aa3d1` based on `416bc2dcca4c6b117249aca02c5293a8e53ffeae`. Feature commit `db571d995714dfbda3ce006f900f9ecb34a315c7` exists; the five later commits to PR head changed handoff/metadata only (verified with GitHub compare).
- Root README declares Python 3.12+, but `backend/app/vision/faces/image_io.py` imports `imghdr`, removed from Python 3.13. Local Python 3.13 suite cannot import application; not evidence of a failure on the user's Python 3.12 Windows machine.

## Independent checks

PASS: ZIP integrity, changed/full file comparison, Python compileall for backend and tests, deterministic isolated AST-based reproduction of cross-request credential deletion (see REPRODUCTION.txt).

NOT INDEPENDENTLY VERIFIED: Cursor reports `295 passed` and `npm audit` zero vulnerabilities. Reports are present and internally check out, but test environment here has Python 3.13 and fails import on `imghdr`; no Windows/EZVIZ integration was available. Production camera gates remain BLOCKED.

## Findings

### P0-01: Shared pending camera-secret deletion queue crosses request transactions (confirmed by isolated reproduction)

Source: `backend/app/api/deps.py:50-52,67-98`, `backend/app/api/cameras.py:877-885`.

`AppState.pending_camera_secret_deletes` is a process-shared list. A camera DELETE adds its `secret_ref` before its own `db.commit()`. ANY other request completing `get_db` can drain the shared queue after its unrelated commit. A later rollback of the camera DELETE cannot undo the earlier file deletion. On exception, a request can also clear another request's queued deletions.

Evidence: isolated execution of the exact `get_db()` function AST with fake database sessions reproduces `Request B commit -> camera-A.bin deleted -> Request A rollback` (no actual file was deleted).

Fix: request/session-scoped pending operations with exact transaction ownership, not AppState-global mutable state; defer cleanup only after matching transaction successfully commits; implement durable/retriable cleanup with audit and idempotency if needed. Test simultaneous A-rollback/B-commit and A-commit/B-rollback cases.

### P0-02: Camera credential replace/remove still mutates the filesystem before SQL commit

Source: `backend/app/api/cameras.py:162-249,642-708`; `backend/app/services/camera_credential_service.py:58-73,75-98`; `backend/app/services/secrets_store.py:50-61,83-105`; `backend/app/api/deps.py:67-99`.

Camera create and update call `apply_camera_credentials()` before the SQL transaction commits. The `replace` path writes `camera-{id}.bin` in place; `remove` deletes it immediately. On DB transaction rollback or a failed `db.commit()`, SQLite state can disagree with the irreversible file mutation. The new P0 tests cover a pre-delete FK blocker and normal deletion, NOT a credential UPDATE/REPLACE/REMOVE followed by simulated DB commit failure.

Fix: use transaction-aware credential staging/versioned refs and atomic post-commit promotion, never overwrite the live credential prior to commit; preserve old credential until new durable state verifies; deferred removal after matching commit; reconcile orphaned staged versions. Test DB flush/commit failure and process crash at each phase.

### P1-03: Camera runtime status can mislead operators

Source: `backend/app/api/overview.py:48-54,71`, `backend/app/api/health.py:63-102`.

Overview labels the camera fleet as mock if *any* CameraDevice is configured MOCK, without consulting healthy LIVE decoder state. The runtime badge uses the first source's `provenance` and can say LIVE without checking `decoder_status` and `operationally_ready`. This matches the user's previous observations of LIVE preview alongside MOCK/header warnings. Use camera-specific operational status and explicit fleet aggregation, distinguish configured from decoded/healthy from CAMERA_LAB approval; never label LIVE based on provenance alone.

### P1-04: HEVC integrity is heuristic, not proof of error-free frames

Source: `backend/app/vision/camera/gateway.py:168-193,538-603,665-710`.

`frame_looks_corrupt()` tests image statistics and large black slabs, not RTP/HEVC bitstream integrity; damaged partial images can evade it. `hevc_ref_events` increments for generic read/decode failures as well as corrupt frames, so its name overstates specificity. Warm-up skips a fixed number of frames, not a verified codec keyframe. More metrics and real A/B are necessary: duration of interruptions, decoder errors by source, good-frame age, stream recovery, CPU/memory, transport, and actual codec. Do not suppress warnings or claim fixed on real camera until 30-minute runs.

### P1-05: Stop/start decoder thread ownership edge case

Source: `backend/app/vision/camera/gateway.py:382-420`. `stop()` waits at most 5 seconds before clearing `_thread` and releasing the capture. If `VideoCapture.read()` is still blocked, a subsequent start can create another worker while the previous one is alive. Add deterministic blocking-read tests and prevent restart until prior reader is definitely retired, or expose STOPPING/FAILED state for operator action.

### P1-06: Biometric duplicate tracking not synchronized across threads and not durable

Source: `backend/app/vision/camera/registry.py:279-290`. Last biometric frame IDs are read and written without the registry lock or persistent idempotency. A concurrent read can race; a process restart resets the local cache. Ensure the database-backed observation idempotency contract provides true exactly-once effects per event, not just per-process frame reuse prevention. Test concurrent requests and crash/restart boundaries.

### P1-07: Handoff manifest provenance inconsistent

`SHA256SUMS.txt` lists hashes that do not match the actual two ZIPs; embedded FINAL_HEAD is not a GitHub-resolvable commit. Regenerate the manifest after final ZIP bytes are frozen, use a standalone manifest outside self-referential archives, and write the pushed GitHub PR SHA. Verify archive/member hashes against the claimed commit in CI.

### P2-08: Mobile camera filter row is visually cramped in the provided screenshot

The packaged `screenshots/after-mobile-camera.png` shows the camera selector card's `Hien da luu tru` checkbox, filter label and `Tat ca` select on a single cramped row; the filter label is partly obscured. Wrap the filter and archived toggle onto separate lines at narrow widths, with readable labels and 44px+ touch targets. This is a visual issue in the MOCK screenshot, not proof of a malfunction with a real camera.

### P2-09: Python version compatibility documentation

README says Python 3.12+; module `image_io.py:6` imports `imghdr`, which no longer exists in Python 3.13. Specify exact supported Python range (e.g. 3.12) or replace `imghdr` with safe magic-byte detection. The owner's 3.12 remains in scope.

### OWNER DECISION: Afternoon time-window specification

`backend/app/core/settings.py` and `backend/app/domain/afternoon_selection.py` explicitly implement v1.5 observation window `[17:00, 23:56)`, prefer photo between 17:55 and 18:00, and use 18:00 as a reference only. Earlier discussions included a narrower 17:00-19:00 monitoring window. This is an intentional v1.5 rule in README, NOT a demonstrated coding bug. Obtain explicit owner sign-off on attendance window vs late/overtime handling; do not change silently.

### OWNER DECISION: Minimum admin password length

`backend/app/api/auth.py:46,221` currently requires at least 10 characters. Owner previously asked to consider 8. This is not an unintentional regression in PR #12; decide security policy separately. For password-only admin accounts, retaining 10+ or longer is safer than reducing it without MFA.

## Verified improvements to preserve

- New six-group desktop navigation and mobile drawer in `frontend/src/components/Layout.tsx`.
- Simplified camera operations with advanced `<details>`, MJPEG preview and safe UI password-display policy in `CameraPage.tsx`.
- Wizard-based Windows Lab in `WindowsLabPage.tsx`, raw JSON hidden under technical details.
- Decoder unhealthy gating and invalidation of previous-good cache in `registry.py` and `gateway.py`; unit tests exist for corrupt/stale/duplicate frames.
- Explicit archive/restore/delete-blockers for camera data, and camera edit prefill with credentials never sent in plaintext.
- Updated Vite and React Router lockfiles; Cursor report says npm audit zero, independent registry audit not performed here.

## Release decision and acceptance gate

DO NOT migrate the owner's live DataDir or use hard-delete/credential update on the production-copy profile until P0-01 and P0-02 are fixed with concurrency/rollback tests and a refreshed hash-verified delivery package. A staging test with a copied disposable DataDir is reasonable after checking correct ACL ownership, SQLite integrity and secrets on the clone.

Before physical acceptance: backup complete stopped DataDir (including SQLite WAL/SHM and secrets); verify safe restore; start/restart three times; preserve Admin sessions/camera secrets; validate EZVIZ LIVE for 30 minutes on owner hardware, one A/B variable at a time; archive/delete test duplicates on disposable profiles only; verify Windows Lab evidence chain and no false CAMERA_LAB_PASS; maintain FACE_PILOT/EXIT_VERIFICATION/INSTALLER as BLOCKED pending actual evidence.
