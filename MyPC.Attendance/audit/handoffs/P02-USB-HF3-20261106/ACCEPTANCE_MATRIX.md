# Acceptance matrix — PID safety V2

| Check | Agent CI | Owner Windows |
|-------|----------|---------------|
| Independent static RED→GREEN (5) | PASS required | — |
| Backend pytest | PASS/SKIP reported | — |
| Frontend tsc/Vitest/build | PASS | — |
| PS 5.1 `$PID` collision absent | static PASS | runtime harness |
| Legacy pid-only Stop refuse | static PASS | runtime |
| Creation required / launcher_creation | static PASS | runtime |
| No venvMarker kill auth | static PASS | runtime |
| Update SHA+stage before stop | static PASS | after Update |
| Diagnose CAPTURE_MAPPING | — | prior PASS retained |
| Start → READY → Stop → port-free | **not claimed** | only if owner authorizes after audit |
| USB frame / 30-min soak / CAMERA_LAB | BLOCKED | BLOCKED |
| FACE_PILOT / INSTALLER / PRODUCTION | BLOCKED | BLOCKED |
