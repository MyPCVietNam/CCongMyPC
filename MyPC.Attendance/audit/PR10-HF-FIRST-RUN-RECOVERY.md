# PR10-HF First-run & Recovery

## First-run

- Empty DB → unique CSPRNG admin secret → Argon2 hash + `must_change_password=true` + `auth_epoch=1`.
- Plaintext written once to `{MYPC_DATA_DIR}/FIRST_RUN_ADMIN.txt` (atomic, 0600, Windows ACL best-effort).
- Never overwrite an existing secret file.
- After successful change-password commit, file is scrubbed/deleted.

## Diagnostics (no secrets)

- `GET /api/v1/auth/profile-status` — pending flag, data_dir, whether secret file present.
- `python scripts/inspect_data_profiles.py` — lists LocalAppData / ProgramData / repo `./data` / `MYPC_DATA_DIR` without printing passwords.

## Offline recovery (OWNER only)

```text
# App STOPPED
python scripts/offline_admin_recovery.py --data-dir "<exact MYPC_DATA_DIR>" --yes-i-understand --reason "lost_password"
```

Interactive: confirmation phrase `RECOVER-ADMIN-PASSWORD`, new password, backup passphrase.  
Produces encrypted `.sqlite3.aes` backup under `recovery_backups/`.  
Does **not** delete employees, attendance, embeddings, or approvals.

## Vietnamese operator note

`401 Sai tên đăng nhập hoặc mật khẩu` khi đổi mật khẩu = mật khẩu hiện tại bị từ chối — **chưa** áp dụng mật khẩu mới. Kiểm tra đúng hồ sơ dữ liệu trước khi dùng recovery.
