# P02Q Test Report

## Environment

| Field | Value |
|-------|-------|
| Platform | Linux cloud agent (no company EZVIZ) |
| Date (Asia/Ho_Chi_Minh) | 2026-11-02 |
| Parent HEAD | `42c75d3f1e5052580d01bae410875f7ac8a26551` |
| Implementation HEAD | `f3937a6287465a8bad9bccdb4cc4b48a17edddc4` |
| Command | `python -m pytest tests/unit tests/integration -q` |
| Result | **118 passed** |
| Frontend | `npm run build` — success |
| Evidence category | UNIT_SYNTHETIC + INTEGRATION (no OWNER_WINDOWS_LIVE) |

## Counts

| Suite | Result |
|-------|--------|
| Unit + integration | 118 PASS |
| REAL_MODEL_LOCAL (weights) | NOT_RUN / optional if zoo weights absent |
| OWNER_WINDOWS_LIVE | NOT_RUN |
| CAMERA_LAB physical | BLOCKED |
| Installer Windows compile | NOT_RUN |

## New / updated tests (selected)

- `test_p02q_rtsp_policy.py`
- `test_p02q_native_geometry.py`
- `test_p02q_immutable_frames.py`
- `test_p02q_adaptive_and_ab.py`
- `test_p02q_ffprobe_and_gateway.py`
- `test_p02q_camera_quality_api.py`
- `test_p00_hf_security.py` updated code `LIVE_NOT_CONFIGURED`

Raw log: `audit/P02Q-pytest-output.txt`

## Honesty

Do **not** treat historical “85 PASS” from PR #4 as freshly re-executed in isolation; this run’s authoritative count is **118** at the commit recorded in SOURCE-CUSTODY / GATES.
