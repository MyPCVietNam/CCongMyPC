# PR5 Corrective A/B Report

- Default effective mode remains **AUTO_TEST_ONLY**.
- `POST .../quality/analyze-once` runs `run_paired_recognition` (ORIGINAL + enhanced copy through FacePipeline).
- `can_auto_enable_enhancement` always false without signed AUTO_VALIDATED approval.
- UNKNOWN→known / wrong-identity on enhance recorded as blockers.
- No real employee faces in public CSV/ZIP. Physical FACE_PILOT still **BLOCKED**.
