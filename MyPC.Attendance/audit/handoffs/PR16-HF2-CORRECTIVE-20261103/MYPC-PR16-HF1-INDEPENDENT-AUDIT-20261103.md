# MyPC Attendance PR16-HF1 - Independent source audit

Date: 2026-11-03. Scope: user-provided `MYPC-PR16-HF1-COMPLETE-AUDIT.zip` only; source review and selected tests. No physical Windows/camera test was performed.

## Baseline and custody

- PR #17 branch tip reported: `78038062f57ccde20e5551fb93cdf8d58d83affd` (base PR16 tip `1bdaef6a7aa63b24127239911fb021dcaf3e147a`).
- Outer ZIP SHA256: `dc4469a3ca93d9f791187218d3b0d03dc3a7b95afea64b014a52a50cd6584297` - MATCH.
- Nested CHANGED SHA256: `9affda24866551bbe94df1087afbb99e82ef94e9bbbbaff9eb16b8548c0850a1` - MATCH.
- Nested FULL SHA256: `e30b792bf925b6ce2f29abf358ee617220ce3fb3ff326b9e145cd0ff14d3c144` - MATCH.
- Nested SAFE EVIDENCE SHA256: `930c8d3d348c8c6a3d6407851ac1d687c48170c2ffbe1e47cd87ae9e2e53e2b9` - MATCH.
- All four ZIPs passed CRC verification. `CHANGED_PATHS.txt` lists 35 files; all 35 appear in CHANGED ZIP. `CODE_PATHS.txt` lists 18 code files; all 18 appear in CHANGED and FULL and are byte-identical.
- `PACKAGE_META.json` records `feature=5671e2b...`, but `FEATURE_COMMIT.txt` records `d7fd6d6...`. Clarify the distinction between code feature commit and packaging freeze commit. `FINAL_HEAD.txt` is packaging freeze `5671e2b...`, not PR tip `7803806...`; do not represent freeze as the final remote tip.

## Independent executions

- Python 3.13.5, pytest 9.0.2, FastAPI 0.128.2, OpenCV 4.13.0: `python -m compileall` - PASS.
- Selected isolated PR16-HF1 unit tests: 14/14 PASS. These test Python logic, NOT TypeScript compilation or browser runtime behavior.
- Integration suite attempted but did not complete within the time budget in this non-pinned runtime; no conclusion about integration PASS/FAIL. The reported 323 tests in the handoff are Cursor evidence, not independently reproduced under the required pinned Python 3.12/FastAPI 0.115.14 runtime.
- `tsc --noEmit --target ES2020 src/camera/diagLanes.ts` - FAIL: TS1003 and TS1138 at line 102. No `node_modules` was available to run a complete Vite bundle; the TypeScript parse error alone is a conclusive build blocker.

## Findings

### F01 - P0 - TypeScript parse/build blocker (confirmed)

File: `frontend/src/camera/diagLanes.ts:99-104`. The function `mjpegWatchdogState(live, *, staleAfterMs = 4000)` uses Python-style bare `*` keyword-only syntax, invalid in TypeScript. Imported from `CameraPage.tsx`, so this blocks frontend compilation. Fix and require actual `tsc` plus `npm ci`/`npm run build` gates, not mirrored Python-only tests.

### F02 - P1 - MJPEG watchdog is decoder-only (confirmed architecture limitation)

Files: `frontend/src/camera/diagLanes.ts:99-116`, `frontend/src/pages/CameraPage.tsx:180-270, 724-744`. The watchdog uses server decoder status and frame age. An MJPEG HTTP path/browser freeze can occur while the decoder keeps producing fresh frames. Do not label this as a verified browser MJPEG transport watchdog. Either add verifiable last client-received frame activity with bounded reconnect, or label the health explicitly as server decoder health and present browser-MJPEG freshness as UNVERIFIED.

### F03 - P1 - Stale SNAPSHOT flag can override healthy MJPEG LIVE (confirmed code path)

Files: `frontend/src/camera/diagLanes.ts:53-83`, `CameraPage.tsx:598-610, 724-757`. `uiStateFromLanes()` prioritizes `preview.stale` and `preview.degraded` without knowing whether the active view is snapshot or MJPEG. `preview` remains cached after switching views, making an old snapshot status override fresh LIVE decoder health. Include active view mode / source generation in state resolution.

### F04 - P1 - Secret auditor falsely exits success if database is absent (reproduced)

File: `tools/audit_camera_secrets_readonly.py:84-157, 211-231`. With an existing `secrets/` directory but no SQLite database, the tool prints zeros and exits 0. Reproduction: create empty temp dir with `secrets/`, execute script with `--data-dir <temp>`, observe exit 0. This is not a valid database/outbox inventory. Make missing/unreadable/ambiguous SQLite and unavailable required schema exit nonzero, with `INCOMPLETE` state and no inferred orphan status. Continue read-only and never destroy/modify files.

### F05 - P1 - Packaging content scanner is not actually fail-closed for secrets (confirmed code path)

File: `tools/package_pr16_hf1_complete_audit.py:23-31, 67-113`. `DENY_CONTENT` is evaluated, but only a `BEGIN ... PRIVATE KEY` match produces a hard fail; other matched token/password patterns do not block. `scan_zip()` checks paths and nested ZIP names but does not comprehensively scan member content. Existing archive passed checksum/CRC, but the 'scanner fail-closed PASS' claim is stronger than the implementation. Implement an auditable, fail-closed content scan suitable for code/test fixtures (explicit vetted dummy allowlist) and recursive nested archive traversal.

### F06 - P1 - Handshake probe can still overwrite operational DB status under a live decoder (code risk)

File: `backend/app/api/cameras.py:629-645`. `AUTH_FAILED`, `STREAM_NOT_FOUND`, `RTSP_DISABLED_OR_UNAVAILABLE` still update `row.connection_status` regardless of whether an independently healthy LIVE gateway exists. Handshake probes may use different auth or a transient transport. Store handshake results distinctly and never let their transient status override an independently verified LIVE runtime; test this specifically with mocked LIVE gateway and auth/path negative probe. Preserve visible errors and audit log.

### F07 - P1 - Evidence eligibility and UI request generations (confirmed code risks)

- `backend/app/services/evidence_store.py:203-229`: when `pins is None`, `pin_ok=True` and evidence with a lab-run ID is returned `eligible_for_sign=true`. Server POST may still reject signing, but GET presents a false positive. Fail closed (`eligible_for_sign=false`, reason `PINS_UNAVAILABLE`).
- `frontend/src/pages/WindowsLabPage.tsx:110-146`: an asynchronous `loadPriorEvidence()` response can set prior evidence/signed flags after camera or lab kind has changed; no request-generation check. Ineligible rows remain selectable and button is enabled if an ID is chosen. Reset/invalidate on camera AND kind changes, ignore stale responses, disable ineligible signing selections. The backend permission and pin checks must remain authoritative.

### F08 - P2 - Unit test gap (confirmed)

`tests/unit/test_pr16_hf1_frontend_diag_lanes.py` is a Python reimplementation of logic from `diagLanes.ts`, not a test that imports/executes the actual TypeScript. It passed despite F01. Add TypeScript/Vite compilation and executable tests against the actual frontend module, plus camera selection/view-mode race tests.

## Recommendation

Status: **HOLD - PR16-HF2 corrective required before Windows staging.** Do not merge PR #17 into main. Camera and PowerShell are currently OFF. Keep production DataDir untouched. Correct F01-F08 on a new branch starting at PR #17 tip, rerun backend and genuine frontend tests, deliver a fresh complete audit ZIP, then perform Windows-only soak, native HEVC A/B, and owner HMAC verification with real hardware. Physical gates remain BLOCKED until that time.
