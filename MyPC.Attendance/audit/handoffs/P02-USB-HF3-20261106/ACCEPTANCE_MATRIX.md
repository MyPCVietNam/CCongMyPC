# Acceptance matrix — PID safety V3

| Check | Agent-local | Owner Windows |
|-------|-------------|---------------|
| Independent V3 static 6 RED→GREEN | PASS required | — |
| Prior V2 independent static 5 GREEN | retained | — |
| Backend pytest | PASS/SKIP reported | — |
| Frontend tsc/Vitest/build | PASS | — |
| Default harness never real Stop-Process | static + mock | after V3 audit |
| Exact `--app-dir` token match | PASS | — |
| Stop fail-closed on live launcher | PASS | after V3 audit |
| Start/Stop/runtime on owner | **not authorized** | only after independent review |
| USB frame / soak / CAMERA_LAB / FACE / INSTALLER / PROD | BLOCKED | BLOCKED |
