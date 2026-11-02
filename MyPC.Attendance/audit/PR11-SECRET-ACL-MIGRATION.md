# Migration / rollback

## Forward (owner Windows)

1. Stop app (port 8765 free).
2. Confirm `-DataDir` is the existing profile (`%LOCALAPPDATA%\MyPC\Attendance\data` or ProgramData — **do not switch**).
3. Optional: copy entire data tree to `backups/pre-secret-acl-hf-<stamp>/`.
4. Deploy this branch; run `Repair-MyPCSecretsAcl.ps1 -CheckOnly` then `-Repair` if needed.
5. Start with same `-DataDir`; restart ≥3 times.
6. Verify login (existing admin — no new bootstrap), camera list, face enrollment templates still decrypt.

## Rollback

1. Stop app.
2. Restore previous app sources if needed.
3. ACL: restore saved `icacls /save` dumps from `backups/secrets-acl-before-*` via `icacls /restore` **only** if required; secret **bytes** were never modified by this HF.
4. Do not restore by regenerating keys.

## Non-goals

- No SQLite schema wipe
- No secret payload rotation
- No CAMERA_LAB PASS without physical evidence
