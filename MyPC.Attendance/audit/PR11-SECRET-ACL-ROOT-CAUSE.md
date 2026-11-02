# Secrets ACL systemic regression — root cause

**Affected tip:** `4ec06cf` (`cursor/pr11-camera-rtsp-hf-83a8`)

## Mechanism

`secrets_store._restrict_windows_acl()` ran `icacls <path> /inheritance:r` then granted `USERNAME:(R,W)` **without `(OI)(CI)`** on the secrets directory, with `check=False` (errors swallowed). Child files created earlier (or with broken inherited ACEs) became unreadable to the normal MyPC user even when the directory listing showed `MyPC:(R,W)`.

Owner evidence sequence:
1. `face_templates.key` PermissionError → one-file ACL grant restored that file only.
2. Next launch: `session.secret` PermissionError in `load_or_create_session_secret` before app ready.
3. Not OpenCV / RTSP / npm / SQLite corruption.

## Fix

Unified `app.core.windows_secrets_acl`:
- Directory ACE: user SID `(OI)(CI)(M)` + SYSTEM `(OI)(CI)(F)`
- Skip destructive inheritance reset when policy already healthy
- `SECRET_ACCESS_DENIED` if existing secret unreadable — never regenerate
- Owner repair scripts (PS1 + Python) scoped to known secret filenames only
