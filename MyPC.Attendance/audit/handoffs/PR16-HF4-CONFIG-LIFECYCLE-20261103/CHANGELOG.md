# PR16-HF4 CHANGELOG
- Add `camera_trust_lifecycle.py` (classify material PATCH, revoke trust, stale binding).
- `update_camera` rotates revision and invalidates trust on material changes; name-only preserved.
- Eligibility: MOCK/disabled/archived, provenance required, NULL expiry fail-closed, PHYSICAL ignores challenge TTL.
- `verify_active_approval(AUTO_VALIDATED)` revalidates CAMERA_LAB+FACE_PILOT deps.
- Tests: audit repro (4), HTTP lifecycle integration, TTL + AUTO_VALIDATED regressions.
- WindowsLab note: signed ≠ operational READY when disabled/MOCK.
