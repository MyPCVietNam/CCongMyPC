# PR6 Follow-up — Source Custody

- **Working repo:** https://github.com/MyPCVietNam/CCongMyPC
- **Audited PR #6:** https://github.com/MyPCVietNam/CCongMyPC/pull/6
- **Audited immutable base:** `36c49b12d0474f03561f7549aa4235a8a5ba3212`
- **Follow-up tip (this PR):** `2b258239680bae2b43365b34f892cf8aed4528d9`
- **Feature branch:** `cursor/pr6-followup-secure-pilot-83a8`
- **Base branch for PR:** `cursor/pr5-corrective-p02q-83a8` (PR #6 head)
- **Instruction date:** 2026-11-02 (Asia/Bangkok)

## Custody rules followed

1. Branched from PR #6 code-bearing HEAD `36c49b1` — no reset, no main merge.
2. Preserved FastAPI/React/SQLite architecture and Vietnamese UI.
3. Baseline before edits: historical 133 was **not** trusted; full suite re-run after changes.
4. Physical CAMERA_LAB / FACE_PILOT / EXIT / INSTALLER remain **BLOCKED** (no fabricated PASS).

## Independent audit package ingested

`MYPC-ATTENDANCE-PR6-INDEPENDENT-AUDIT-FOLLOWUP-20261102` (tools + matrix + review).
Standalone SQLite reproducers confirm naive/aware TypeError and isoformat HMAC drift; app fix uses Zulu `payload_json` HMAC + UTC helpers.
