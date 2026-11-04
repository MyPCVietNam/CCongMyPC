# MyPC Attendance — P02 REAL Face Detection + ROI Overlay

**Baseline (HF5 / PR #21 tip):** `2808ff3c45f8f1a68f57b81c9caf87475ca315cd`  
**Branch:** `cursor/p02-real-face-overlay-83a8`  
**Download:** `MYPC-P02-REAL-FACE-OVERLAY-COMPLETE-AUDIT.zip`

## Phase
DETECTION + QUALITY only on CAMERA_LIVE frames via existing YuNet `FacePipeline.detect_and_quality`.  
**Not** identity recognition, **not** FACE_PILOT, **not** attendance, **not** LIVE_STABILITY_PASS.

## Contents
A/B/C ZIPs + manifests. Tests use synthetic frames only.

**Do not merge to main. Physical Windows gates remain BLOCKED.**
