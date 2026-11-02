# Secrets ACL HF changelog

- Add `backend/app/core/windows_secrets_acl.py` — SID-based inheritable ACL, fail-closed access.
- Wire `secret_bootstrap`, `SecretsStore`, `MediaCrypto` to never regenerate inaccessible keys.
- Remove broken non-propagating `_restrict_windows_acl` from secrets_store.
- Add `scripts/repair_secrets_acl.py` + `scripts/windows/Repair-MyPCSecretsAcl.ps1` (UTF-8 BOM).
- Vietnamese operator guide + Windows matrix (physical BLOCKED until owner evidence).
- Unit tests for SECRET_ACCESS_DENIED / byte stability.
