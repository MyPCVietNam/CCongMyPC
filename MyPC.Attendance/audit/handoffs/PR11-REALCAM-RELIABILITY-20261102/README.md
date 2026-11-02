# MyPC Attendance - PR11 Real Camera Reliability Handoff

**Purpose:** Cursor implementation contract following the first successful physical EZVIZ H8 Pro 3K LIVE decode on Windows, with remaining image corruption, camera delete/profile, state-machine and UX defects.

## Contents
- `CURSOR_MASTER_PROMPT.md`: Full implementation task (English, ready for Cursor).
- `EVIDENCE_AND_LIMITS.md`: Evidence, source URLs and explicitly unverified facts.
- `ACCEPTANCE_MATRIX.md`: Test cases and evidence contract.
- `README.md`: Package use and safety rules.
- `SHA256SUMS.txt`: Hashes of package members.

## What the owner sends Cursor
Attach this ZIP with the message: "Read CURSOR_MASTER_PROMPT.md and all bundled supporting files. Implement the entire corrective phase against the verified PR11 Secrets ACL branch, and ship separate changed-source and full-source ZIPs with hashes. Do not merge main or fake physical gate PASS."

## Current owner operations
Do not wipe any SQLite/secrets to delete profile duplicates. Do not enable a MOCK profile to pass physical Camera Lab. Keep the known working camera #1 and the existing `%LOCALAPPDATA%\MyPC\Attendance\data` unchanged until the corrected build and backup are verified. Back up with the app stopped; secrets are sensitive. Never send password fields or raw employee face frames to Cursor.

## Evidence standard
This handoff does not include a full checkout, does not contain user images/log files, and does not declare the entire source audited. Targeted source inspection identified browser preview polling and CRUD UI flows. Cursor must audit and test the full source checkout, and the owner must provide physical validation.
