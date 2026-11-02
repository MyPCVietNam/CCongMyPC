# PR10-HF Security

## Controls added

1. **Forced password change (server + UI)** — pending users only reach login/me/change-password/logout/health/diagnostics/profile-status/runtime-badge.
2. **Durable session revocation** — `auth_sessions` rows + `auth_epoch`; survives restart; old signed cookies fail.
3. **Change-password ordering** — verify current password + CSRF; bump epoch; revoke sessions; audit without secrets; delete `FIRST_RUN_ADMIN.txt` only after DB commit.
4. **Offline recovery** — `scripts/offline_admin_recovery.py`: exclusive lock, typed confirmation, encrypted backup, interactive passwords (not argv), no employee/attendance wipe, `must_change_password=true`.
5. **No default/static admin password** — CSPRNG bootstrap; existing DB never re-bootstrapped.
6. **Login rate limit** — bounded lockout; generic 401 message (no username enumeration).
7. **Mock ingest** — not silently allowed in `development` alone.

## Residual risk

- Windows DACL effective-rights not measured on this Linux agent (AUTH-34 BLOCKED).
- npm advisories on Vite/esbuild (dev server) and react-router (see DEPENDENCY-AUDIT) — no `npm audit fix --force`.
- Installer / CAMERA_LAB / FACE_PILOT / EXIT still BLOCKED without physical evidence.
