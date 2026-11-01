# P01.5-HF Test Report

**Date:** 2026-11-02 (Asia/Saigon)  
**Baseline:** PR #3 `f8acf2548cdf02d61df40b2590b8237b29c1e169`  
**Branch:** `cursor/p015-hf-p02-camera-gateway-83a8`

## Commands

```
cd MyPC.Attendance
. .venv/bin/activate
export PYTHONPATH=backend
pytest tests/unit tests/integration -q
cd frontend && npm run build
```

## Results (this Linux agent environment)

- **85 passed** (unit + integration)
- Frontend Vite build: **PASS**
- Real-model SFace tests: included in suite when weights present

## HF gates

| Gate | Status |
|------|--------|
| P015_PLAINTEXT_EMBEDDING | **PASS** (DB-level assert + scrub migration) |
| PRODUCTION_SYNTHETIC_BYPASS | **PASS** (403 SYNTHETIC_FIXTURE_DENIED) |
| DEMO provenance not remapped to AUTO | **PASS** |
| Encrypted body image roundtrip (DEMO testing_mode) | **PASS** |
| Real YOLOX person detector production | **BLOCKED** (no licensed weights; synthetic only in testing_mode) |
| CAMERA_LAB / FACE_PILOT / WINDOWS / INSTALLER | **BLOCKED** |
