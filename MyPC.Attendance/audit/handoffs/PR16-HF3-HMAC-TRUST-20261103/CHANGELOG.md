# PR16-HF3 CHANGELOG

## Backend

- `evidence_store.py`: add `SignEligibility`, `evaluate_physical_sign_eligibility`, `revoke_physical_evidence_for_camera`; list/require reuse the evaluator.
- `cameras.py` configure/rebind: revoke physical evidence on `CAMERA_CONFIG_REVISION_CHANGED` (with approvals + lab runs).
- `pilot_approval.py` `verify_active_approval`: after HMAC/pins/expiry, re-check CAMERA_LAB/FACE_PILOT backing evidence via the shared evaluator (AUTO_VALIDATED unchanged).

## Frontend

- `lab/signOpGuard.ts` + vitest deferred-Promise races.
- `WindowsLabPage.tsx`: selection epoch fence for sign POST → evidence reload → gateway health.
- `diagLanes.ts` / `CameraPage.tsx`: browser MJPEG stays UNVERIFIED without verified multipart heartbeat; do not claim LIVE_STABILITY_PASS from `onLoad`.

## Tests

- `tests/unit/test_reject_stale_physical_evidence.py` (supplied audit repro, adapted) — PASS.
- `tests/integration/test_pr16_hf3_hmac_trust_chain.py` — REST negatives, fresh sign, post-sign revoke, reconfigure revoke.
- Updated HF2 pins eligibility, PR6/PR7 fixtures for live lab-run backing.
