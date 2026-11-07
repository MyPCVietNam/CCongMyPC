# Source and evidence packaging contract

Deliver separately:

- `MyPC.Attendance-FULL-SOURCE-<phase>.zip`: all source required to reproduce the build; exclude owner data, secrets, binary weights, runtime files and `.git`.
- `MyPC.Attendance-CHANGED-SOURCE-<phase>.zip`: changed/added files plus manifest of relative paths, deletions, and changelog.
- `MYPC-<phase>-WINDOWS-SAFE-EVIDENCE.zip`: redacted counters, test matrices, commands/results, owner gate statuses; no biometrics, raw PnP/DevicePath, passwords/HMAC or complete unrestricted logs.
- `MYPC-<phase>-COMPLETE-AUDIT.zip`: contains the above, SHA256SUMS and immutable commit metadata.

Test and verify each ZIP CRC/path safety, full SHA256 and manifest. Distinguish feature SHA, freeze SHA and remote HEAD. If HEAD moves after freeze, record both (do not silently rewrite immutable artifact). Do not claim a CI PASS without a GitHub check run against the exact reviewed SHA. Always state physical gates as BLOCKED until authorized evidence.
