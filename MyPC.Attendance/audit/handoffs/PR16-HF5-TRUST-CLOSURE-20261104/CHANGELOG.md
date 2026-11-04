# PR16-HF5 CHANGELOG

- `merge_effective_credential_change`: after credential apply on PATCH, treat any `CredentialApplyResult.changed` as MATERIAL (including keep+password / keep+username rewrite).
- Invalid `credential_action` → HTTP 422 on PATCH and configure LIVE (no secret write).
- Configure LIVE revokes physical trust on effective credential change (`cred.changed`).
- AUTO_VALIDATED `verify_active_approval` re-checks linked `AbEvaluationRun` (promotable, pins, config_revision, same camera).
- Audit repros under `tests/unit/` + HTTP/DB integration `test_pr16_hf5_credential_and_ab.py` (synthetic credentials only).
- HF4 AUTO_VALIDATED fixture updated with promotable AB row for verifier compatibility.
- Static frontend bundle refreshed (`index-BRx11ug4.js`).
- Owner Windows commissioning checklist + read-only `tools/owner_windows_safe_evidence.ps1`.
- Packaging: four ZIPs + COMPLETE via `tools/package_pr16_hf5_complete_audit.py`.
