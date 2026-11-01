# P02 Release Gates

| Gate | Status | Notes |
|------|--------|-------|
| P015_PLAINTEXT_EMBEDDING | PASS | HF |
| PRODUCTION_SYNTHETIC_BYPASS | PASS | HF |
| UNIT / API_INTEGRATION / FRONTEND_BUILD | PASS | 85 tests; Vite build |
| P02_MOCK gateway | PASS | MockFrameGateway + health |
| P02_WINDOWS | BLOCKED | No Win11 host in agent |
| CAMERA_LAB | BLOCKED | No EZVIZ decode evidence |
| FACE_PILOT | BLOCKED | Depends on CAMERA_LAB |
| EXIT_VERIFICATION | BLOCKED | Later |
| INSTALLER | BLOCKED | PowerShell ≠ signed installer |
| SECURITY | PASS (code) / residual cleanup notes | See P015-HF-SECURITY-REPORT |
