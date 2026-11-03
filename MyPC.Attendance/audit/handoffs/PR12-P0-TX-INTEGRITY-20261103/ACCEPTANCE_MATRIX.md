# Acceptance — PR #12 P0 transactional integrity correction

| ID | Item | Status |
| --- | --- | --- |
| P0-01 | Session-scoped secret FS outbox (no AppState-global drain) | PASS |
| P0-02 | Staged REPLACE / deferred REMOVE; live preserved on rollback | PASS |
| P1-03 | Honest fleet / runtime badge (LIVE only if operationally ready) | PASS |
| P1-04 | HEVC heuristic honesty; generic decode ≠ hevc_ref_events | PASS (code); physical A/B BLOCKED |
| P1-05 | stop/join ownership — no second reader while prior alive | PASS |
| P1-06 | Biometric frame_id dedupe under registry lock | PASS |
| P1-07 | Manifest regenerated after ZIP freeze; FINAL_HEAD = GitHub tip | PASS (packaging) |
| P2-08 | Mobile camera filter row wrap + 44px targets | PASS |
| P2-09 | imghdr removed; magic-byte detection | PASS |
| G-* | CAMERA_LAB / FACE_PILOT / EXIT / INSTALLER | BLOCKED |

Business rule v1.5 afternoon window unchanged — owner sign-off required to change.
