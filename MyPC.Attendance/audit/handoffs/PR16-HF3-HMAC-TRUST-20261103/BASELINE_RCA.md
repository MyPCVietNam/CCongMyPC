# PR16-HF3 — Root cause analysis (HMAC physical evidence trust chain)

## Baseline

- Upstream PR: GitHub #18 (OPEN) tip `1fa4a1c47196089a61da9ad91d524e7e2e56b80f`
- Branch created from that exact commit: `cursor/pr16-hf3-hmac-trust-83a8`
- Independent audit input: `MYPC-PR16-HF2-AUDIT-HF3-HANDOFF.zip`

## P0 defect (independently reproduced)

`list_physical_evidence_for_camera()` / `require_physical_evidence()` treated a nonempty `lab_run_id` string plus matching model/gallery/threshold pins as sufficient for `eligible_for_sign` / `valid`. They did **not** require:

1. A real `CameraLabRun` row
2. Lab run `state == PHYSICAL_VERIFIED`
3. Lab run not revoked / not expired
4. Lab run camera/kind match
5. Full `config_revision` equality with current `CameraDevice` (and binding when present)

Camera reconfigure revoked HMAC approvals and lab runs but left `PilotEvidenceRecord` rows unrevoked and still signable. Therefore stale PHYSICAL evidence from a prior revision could authorize a new CAMERA_LAB HMAC after reconfigure. A nonexistent `lab_run_id` was also accepted.

This is a server trust-chain verification flaw proven with synthetic SQLite — not evidence of an external exploit against a live deployment.

## Fix

1. Single authoritative `evaluate_physical_sign_eligibility()` used by listing, POST `/quality/approvals`, and `verify_active_approval()` for CAMERA_LAB / FACE_PILOT.
2. Reconfigure path also calls `revoke_physical_evidence_for_camera()` (audit rows retained, `revoked=True`).
3. `verify_active_approval()` re-validates backing evidence/lab/config/pins after HMAC+expiry checks; invalid backing ⇒ gate closed without deleting the signed payload.
4. Safe reason codes: `LAB_RUN_MISSING`, `LAB_RUN_REVOKED`, `LAB_RUN_STATE_INVALID`, `LAB_RUN_EXPIRED`, `LAB_RUN_MISMATCH`, `CONFIG_REVISION_MISMATCH`, `EVIDENCE_REVOKED`, `PIN_MISMATCH`, `EVIDENCE_NOT_PHYSICAL`, `PINS_UNAVAILABLE`, etc.

## P1 / P2

- Windows Lab signing: selection epoch + immutable camera/kind fence on all post-await UI updates.
- Browser MJPEG: `<img onLoad>` is not a multipart frame heartbeat; browser transport stays `UNVERIFIED` unless `multipartHeartbeatVerified=true`.
- Packaging: freeze commit ≠ remote tip; sidecars labeled explicitly (see `FREEZE_VS_TIP_TIMELINE.md`).

## Gates still BLOCKED (owner Windows only)

LIVE_STABILITY_PASS, FACE_PILOT, INSTALLER, production attendance, physical soak/HEVC native RCA — camera/runtime currently OFF.
