# Architecture decisions (PR16-HF5)

## Effective vs declared credential action
Trust invalidation uses actual `CredentialApplyResult.changed`, not the client `credential_action` string alone. Declared `keep` may still be material after `apply_camera_credentials` (implicit password replace; username re-encrypt with stored password). Callers merge via `merge_effective_credential_change` after apply. Unknown actions → HTTP 422 with no secret write.

## Material invalidation contract
On effective material change: rotate `CameraDevice.config_revision`, revoke CAMERA_LAB / FACE_PILOT / AUTO_VALIDATED approvals, revoke backed PHYSICAL evidence and lab runs (audit history retained), stale-mark `CameraLiveBinding`, unbind runtime, report `NEEDS_REBIND` + sanitized reasons. Secret outbox stage/promote and redaction preserved; failures fail closed.

## Configure LIVE
`POST /gateway/live/configure` rejects invalid `credential_action` (422). Any `cred.changed` revokes physical trust before rebind. Host/RTSP path changes continue to rotate LIVE identity.

## AUTO_VALIDATED AB backing
Every `verify_active_approval` for AUTO_VALIDATED reloads `AbEvaluationRun` by signed `ab_run_id`, requires same camera, `ab_run_promotable()`, and matching model/gallery/threshold pins + config_revision when recorded. Missing/mismatched AB ⇒ DENY. CAMERA_LAB / FACE_PILOT deps still re-verified (no recursive AUTO loop; AB check is a single row load).

## Safe non-material cases
Name-only edits; blank-password keep with same username; enable/disable with unchanged source — no forced re-lab. Disabled still closes operational gate. Explicit replace/remove always material.
