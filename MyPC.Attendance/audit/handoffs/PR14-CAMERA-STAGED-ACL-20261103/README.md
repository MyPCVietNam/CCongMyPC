# PR14 hotfix — Windows camera staged secret ACL

**Feature:** `527fcb993d5182b9d758c8940678aec412ed1a0f`  
**Base:** PR #14 `cursor/pr13-release-safety-83a8`

## Bug
Windows `apply_new_secret_file_acl` rejected `camera-1.staged-<uuid>.bin` because allowlist only matched `camera-<id>.bin`.

## Fix
Least-privilege staged pattern + scrub on ACL failure + regression tests.

## Verify
- Cloud: 301 pytest PASS (Python 3.12.3, FastAPI 0.115.14)
- Owner Windows: create LIVE camera with credentials; confirm promote; no orphan staged; ACL applied
- CAMERA_LAB = **BLOCKED** until RTSP/HEVC owner evidence
