# P01 TEST REPORT — Face enrollment / recognition

| Field | Value |
|-------|-------|
| Platform | Linux 6.12 cloud agent, Python 3.12.3 |
| Command | `pytest tests/unit tests/integration -q` |
| Result | **62 passed** |
| Timestamp (Asia/Ho_Chi_Minh) | 2026-11-02 |

## Gate matrix

| Gate | Status | Evidence |
|------|--------|----------|
| SOURCE_CUSTODY | PASS | Branch from faf23d2, tag checkpoint |
| P00_SECURITY | PASS | `test_p00_hf_security.py` |
| MODEL_LICENSE | PASS | YuNet MIT, SFace Apache-2.0 (opencv_zoo) |
| MODEL_INTEGRITY | PASS (download verified) | See `models/manifest.json` SHA256; weights **not** committed |
| UNIT | PASS | AM/PM/OT + face matcher/encryption |
| API_INTEGRATION | PASS | Enrollment DEMO + production mock block |
| FRONTEND_BUILD | PASS | `npm run build` |
| MOCK_REPLAY | PASS | Synthetic fixture identity |
| WINDOWS_RUNTIME | BLOCKED | No Windows host on agent |
| CAMERA_LAB | BLOCKED | No live RTSP decode |
| FACE_PILOT | BLOCKED | No physical shop pilot |
| EXIT_VERIFICATION | BLOCKED | By design |
| INSTALLER_BUILD | BLOCKED | Not in scope |
| PHYSICAL_OPERATION | BLOCKED | Owner Windows PC required |

## Models verified (downloaded locally, not in Git)

| Model | SHA256 | Bytes |
|-------|--------|-------|
| face_detection_yunet_2023mar.onnx | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` | 232589 |
| face_recognition_sface_2021dec.onnx | `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79` | 38696353 |

CI uses `synthetic_fixture` backend when weights absent from `models_dir` test temp path.
