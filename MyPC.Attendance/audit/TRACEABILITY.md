# Traceability matrix (P00-HF + P01)

| Spec requirement | Module | Test | Result |
|------------------|--------|------|--------|
| Mock ingest blocked in production | `api/attendance.py` | `test_mock_observation_blocked_in_production` | PASS |
| DEMO permission required | `core/permissions.py` | `test_mock_observation_requires_demo_permission` | PASS |
| CAMERA_MANAGE + ROI bounds | `api/cameras.py`, `core/validation.py` | `test_roi_validation_rejects_invalid` | PASS |
| SSRF host/URL guards | `core/validation.py` | `test_camera_host_ssrf_blocked` | PASS |
| No silent live→mock preview | `api/cameras.py` | `test_live_preview_no_silent_mock_substitute` | PASS |
| CSRF per session id | `api/deps.py`, `api/auth.py` | `test_csrf_two_sessions_independent` | PASS |
| Idempotent observations | `services/attendance_service.py` | `test_idempotent_mock_replay` | PASS |
| PM 17:00–23:55 / no 18:00 fabricate | `domain/afternoon_selection.py` | unit PM01–PM20 | PASS |
| Encrypted templates | `vision/faces/template_store.py` | `test_template_encryption_roundtrip` | PASS |
| MATCH/UNKNOWN/AMBIGUOUS | `vision/faces/matcher.py` | `test_face_matcher.py` | PASS |
| Enrollment DEMO + revoke | `api/enrollment.py` | `test_p01_enrollment.py` | PASS |
| REAL_CAMERA enrollment blocked | `api/enrollment.py` | `test_real_camera_enrollment_blocked` | PASS |
