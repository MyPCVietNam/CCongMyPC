# Changelog — camera staged ACL hotfix

- `windows_secrets_acl.py`: allowlist LIVE `camera-<n>.bin` and staged `camera-<n>.staged-<32 lowercase hex>.bin` only.
- Reject path smuggling, short/long tokens, uppercase, dashed UUIDs, wildcards.
- `secrets_store._write_encrypted`: wipe+unlink blob if `apply_new_secret_file_acl` fails (no unmanaged temp credentials).
- `_validate_ref` tightened to the same regexes.
- Repair PS1 scripts recognize staged filenames for ACL repair.
- Tests: `test_windows_camera_staged_acl.py` + updated known-name checks.
- No attendance-rule/UX changes. CAMERA_LAB still BLOCKED pending owner RTSP/HEVC.
