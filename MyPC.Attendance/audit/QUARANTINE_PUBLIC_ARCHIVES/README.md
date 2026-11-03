# Quarantine — public archive exposure (SECURITY-P0)

**Do not open, extract, or republish quarantined binaries.**  
Inventory files list **entry names only** — never secret values.

## What happened

Public FULL-source handoff ZIPs under `audit/handoffs/` were built with a recursive tree walk that included untracked `MyPC.Attendance/data/` (SQLite DBs, `secrets/*.key`, `FIRST_RUN_ADMIN.txt`). `.gitignore` does **not** protect ZIP packaging.

## Contained in this PR

- Contaminated `.zip` binaries removed from the working tree and replaced with `*.zip.QUARANTINED.md` placeholders.
- Path inventories written beside this README (`*.QUARANTINED.txt`).
- New packaging: `tools/package_clean_source_zips.py` (git-tracked allowlist) + `tools/sensitive_path_scanner.py` (fail-closed, including nested ZIPs).

## Owner-required follow-up (outside agent scope)

1. **Assume exposure** of any usable credentials / session signing keys / template keys until proven otherwise; rotate and revoke.
2. **Encrypted biometrics:** rotating `face_templates.key` without a controlled re-wrap/migration makes templates unreadable — plan carefully.
3. **Git history rewrite** (filter-repo/BFG) under an owner-approved workflow — deleting only the tip commit is **insufficient** because historic blobs remain reachable.
4. After freeze, publish **new** clean CHANGED/FULL ZIPs and independent external SHA256.

Physical CAMERA_LAB / FACE_PILOT / EXIT_VERIFICATION / INSTALLER gates remain **BLOCKED**.
