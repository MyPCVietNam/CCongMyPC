# PR6 Follow-up — Real A/B Evidence

## What was proven in CI (Linux)

- Empty ACTIVE gallery → `BLOCKED_GALLERY` (unit + analyze-once API).
- Synthetic pipeline → `DEMO_SYNTHETIC` (never accuracy PASS).
- Missing weights → `BLOCKED_MODEL`.
- Paired ORIGINAL vs ENHANCED runs only when REAL mode + nonempty gallery → `REAL_VALIDATION` label; `can_auto_enable_enhancement` always false.
- Offline `evaluate_pairs` still refuses auto-enable (prior P02Q/PR5 tests).

## What was NOT proven

- No physical EZVIZ frames.
- No authorized employee face photos in this environment.
- No DAY/DUSK/NIGHT_IR stratified LIVE pilot.
- No production AUTO_VALIDATED promotion.

Owner must run Windows lab with consenting labeled samples and signed CAMERA_LAB/FACE_PILOT before any production biometric claim.
