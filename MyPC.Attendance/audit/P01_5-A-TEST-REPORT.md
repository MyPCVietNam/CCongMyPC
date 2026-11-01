# MyPC Attendance — P01.5-A Test Report

**Date:** 2026-11-02 (Asia/Saigon)  
**Baseline:** PR #2 `cursor/p00-hf-p01-face-enrollment-83a8` @ `89a56410110c1c89f6d9fc2210c9fe0f23896fdb`  
**Branch:** `cursor/p01-5-auto-enrollment-83a8`

## Critical fix

`FacePipeline.embed_image()` previously called `embed(..., aligned_crop=None)`, so the SFace branch never ran and real images could get synthetic byte-seeded vectors. Production path is now:

1. YuNet detection row (bbox + 5 landmarks + score) preserved as `FaceBox.yunet_row`
2. `cv2.FaceRecognizerSF.alignCrop(original_bgr, yunet_row)`
3. `cv2.FaceRecognizerSF.feature(aligned)` → finite check → L2 normalize
4. Real images **never** enter the synthetic hash branch (`SYNTHETIC_FALLBACK_FORBIDDEN`)

## Decode / lifecycle / quality

- Fail-closed JPEG/PNG decode (`image_io.py`); HTTP 422 with Vietnamese codes; no gray synthetic success on corrupt upload
- Enrollment lifecycle: `DRAFT → CAPTURING → QUALITY_REVIEW → VALIDATING → ACTIVE` (also PAUSED/FAILED/CANCELLED/REVOKED)
- Old ACTIVE templates retained until new enrollment independently verifies and activates
- Quality hard gates: face width ≥120 px (preferred 160), inter-eye, Laplacian variance, illumination, margins; hard fail overrides weighted score
- Matcher aggregates **best-by-identity** before top-two margin (multi-template same employee is not AMBIGUOUS)

## Test results (Linux CI / this agent environment)

```
76 passed (unit + integration)
```

Real-model suite (`pytest -m real_model`):

| Test | Result |
|------|--------|
| Model SHA256 vs manifest | PASS |
| alignCrop + feature ≠ byte-hash; distinct images differ | PASS |
| Missing landmarks fail closed | PASS |
| Corrupt hash rejected | PASS |

Synthetic/fixture suite remains separately labeled; DEMO never publishes production attendance.

## Gates

| Gate | Status | Evidence |
|------|--------|----------|
| SOURCE_CUSTODY | PASS | Branched from 89a5641; history preserved |
| P01_REAL_EMBEDDING | PASS | Real ONNX alignCrop+feature exercised locally |
| MODEL_HASH | PASS | YuNet/SFace SHA256 match `models/manifest.json` |
| MODEL_LICENSE | PASS | OpenCV Zoo Apache-2.0; weights not committed to Git |
| UNIT | PASS | 76 passed |
| API_INTEGRATION | PASS | Enrollment activate / decode reject / keep-old-active |
| MOCK_REPLAY | PASS | Fixture path isolated |
| CAMERA_LAB | **BLOCKED** | No Windows EZVIZ RTSP lab in this environment |
| FACE_PILOT | **BLOCKED** | Requires CAMERA_LAB |
| WINDOWS_RUNTIME | **BLOCKED** | Not run on company Windows PC |
| INSTALLER | **BLOCKED** | Not produced/verified this phase |
| EXIT_VERIFICATION | **BLOCKED** | Later gate |

## Blockers (honest)

1. Physical EZVIZ CS-H8 camera ONVIF/RTSP decode on Windows unverified
2. Real employee photo pilot not performed
3. Experimental quality thresholds (120 px / Laplacian) need calibration on installed camera
