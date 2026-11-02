# P02R Gates

Allowed statuses: PASS / FAIL / BLOCKED / NOT_RUN

| Gate | Status | Evidence |
|------|--------|----------|
| PR8 source ancestry / Cloud verify | **PASS** | `verify_pr8_checkout.sh` |
| Cloud setup idempotent | **PASS** | setup ×2, tracked clean |
| Cloud start + health localhost | **PASS** | HTTP 200 DEMO/MOCK |
| Full pytest | **PASS** | 205 passed |
| Frontend build | **PASS** | vite build |
| Lab-run PHYSICAL FSM (unit/integration) | **PASS** | EV01/EV02/EV05/EV11 tests |
| CAMERA_LAB (physical) | **BLOCKED** | No Windows LAN EZVIZ |
| FACE_PILOT (physical) | **BLOCKED** | No consented LIVE cases |
| EXIT_VERIFICATION | **BLOCKED** | Unchanged |
| INSTALLER | **BLOCKED** | No Windows .exe proof |
| MERGE_MAIN | **NOT_RUN** | Feature PR only |
