## MyPC Change Safety Checklist

- [ ] Base ref, immutable BASE SHA and HEAD SHA recorded; `main` source presence verified.
- [ ] Scope/impact map and rollback plan attached. No unrelated feature changes.
- [ ] Baseline RED proof (which defect, which test), new GREEN and adversarial tests.
- [ ] `guard-contract`, `windows-contract`, `backend-linux`, `frontend` checks all green on the exact reviewed commit.
- [ ] No real Stop-Process/camera/biometrics/owner SQLite in synthetic tests or CI.
- [ ] Physical statuses reported separately; no automatic CAMERA_LAB or production gates.
- [ ] FULL/CHANGED/SAFE-EVIDENCE/COMPLETE ZIP, SHA256SUMS, relative paths, changelog and test skips included.

### Test matrix

| Environment | Command | Passed | Skipped | Blockers |
|---|---|---|---|---|
| Linux/backend | | | | |
| Windows PS 5.1/Pester | | | | |
| Frontend | | | | |
| Owner physical lab (only if authorized) | | | | |

### Security / data custody

Describe changes to Camera/HMAC trust, secrets, DataDir, process ownership, migrations, API auth and privacy. If none, say `No material impact` with rationale.
