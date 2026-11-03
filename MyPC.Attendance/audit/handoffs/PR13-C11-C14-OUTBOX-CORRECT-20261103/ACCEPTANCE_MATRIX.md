# PR13 C11–C14 Corrective — Acceptance Matrix

| ID | Fault | Result |
|----|-------|--------|
| C01–C10 | Prior SQLite crash matrix | PASS (retained) |
| A01–A02 | Retry SETTINGS_APPLY + diagnostics redact | PASS (retained) |
| C11 | Concurrent retry must not scrub in-flight staged | PASS |
| C12 | PATCH name/host/model + REPLACE keeps dirty metadata | PASS |
| C13 | Postcommit FS failure → real HTTP 503 SECRET_FS_OUTBOX_INCOMPLETE | PASS |
| C14 | SQLite PK reuse: old DELETE must not scrub new instance secret | PASS |

Physical CAMERA_LAB / FACE_PILOT / EXIT / INSTALLER = **BLOCKED**.
