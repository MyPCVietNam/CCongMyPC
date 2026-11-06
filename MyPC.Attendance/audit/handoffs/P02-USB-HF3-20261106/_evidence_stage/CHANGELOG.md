# P02-USB-HF3 changelog

## Corrective on PR #26 (`146d04c`)

- Replace invalid `Dispatch('SystemDeviceEnum')` with typed COM `ICreateDevEnum`.
- Enumerate video capture category only; require DevicePath for trust.
- Exclude microphone/camera-audio PnP from video candidates.
- HF3 candidate Prepare/Preflight/Start/Stop/Diagnose/SafeExport on 18878 new DataDir.
- Fix pip via `python -m pip`; resolve manifest `models[]` SHA256 pins (YuNet+SFace).
- Unit/integration regressions for ProgID ban, DevicePath mapping, ambiguity, reorder.
