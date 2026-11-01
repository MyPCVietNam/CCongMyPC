# Architecture — MyPC Attendance

## Processes

1. **Camera Gateway** — ONVIF/RTSP ingest via go2rtc (localhost-only). Secrets stay on host.
2. **Attendance Core Service** — FastAPI, scheduler, CV workers, rules engine, SQLite, reports.
3. **Web UI** — React+Vite static bundle served by Core at `127.0.0.1:8765` by default.

## Design principles

- Offline-first; no mandatory cloud or SaaS.
- Deterministic clock injection for tests.
- Immutable raw observations; derived attendance events are versioned.
- Biometric templates encrypted separately from reporting data.
- Mock Camera / Replay Mode for development without live credentials.

## v1.5 attendance clock model

Three independent afternoon timestamps (never combined):

| Field | Meaning |
|-------|---------|
| `afternoonFirstObservedAt` | First confident match in [17:00, 23:56) |
| `afternoonReferenceObservedAt` | Selected official PM recognition nearest 18:00 |
| `afternoonPrimaryPhotoCapturedAt` | Capture time of preferred face photo |
| `lastObservedAt` | Last reliable sighting |
| `verifiedExitAt` | Verified departure only |

Afternoon recognition window default: `[17:00:00, 23:56:00)` local (`Asia/Ho_Chi_Minh`).  
Reference anchor: `18:00:00` (selection preference, never a fabricated observation time).

## Decision gates (status vocabulary)

- `UNIT_PASS` / `MOCK_INTEGRATION_PASS`
- `WINDOWS_INSTALL_PASS` / `CAMERA_LAB_PASS`
- `FACE_PILOT_PASS` / `EXIT_VERIFICATION_PASS` / `PHYSICAL_OPERATION_PASS`

Do not claim production readiness for camera-dependent features without the matching gate.
