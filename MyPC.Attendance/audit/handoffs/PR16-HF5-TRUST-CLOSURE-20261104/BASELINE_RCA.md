# PR16-HF5 RCA

## Baseline
PR #20 tip `56660d0ddd7fb48883f6789400e28ab72a09825e` (HF4).

## P0 — Effective credential mutation under keep
`classify_camera_update` treated declared `credential_action=keep` as non-material, but `apply_camera_credentials` can still change the secret (nonempty password → implicit replace; username change re-encrypts with stored password) while returning `changed=True` / action still `keep`. HMAC/PHYSICAL stayed active.

**Fix:** After credential apply, `merge_effective_credential_change` promotes the plan when `CredentialApplyResult.changed`. Invalid credential_action → HTTP 422. Configure LIVE also revokes on effective credential change. Audit reason records declared vs effective action (no secrets).

## P1 — AUTO_VALIDATED AB backing
Verifier rechecked CAMERA_LAB/FACE_PILOT but not the linked `AbEvaluationRun`. Missing/rejected/non-promotable AB still looked valid.

**Fix:** On AUTO_VALIDATED verify, require real AB by signed `ab_run_id`, same camera, `ab_run_promotable()`, matching pins and config_revision when present.
