# P02-USB-HF3 changelog

## Patch on PR #27 (identity boundary — in-place)

- **P0:** Remove unsafe `capture_instances_match` heuristics (`na in nb` / VID+PID+trailing-instance ignoring MI).
- Require exact canonical USB video-function identity: VID + PID + MI + complete instance token (`parse_usb_video_function_id`).
- Enforce 1:1 PnP↔DevicePath bijection in `_link_wmi_to_dshow`.
- Balance `CoInitialize`/`CoUninitialize` for the enum call only.
- Harden HF3 Start/Stop: refuse unrelated 18878 owners; require HTTP 200 + `status`/`startup_phase` health payload; never kill stale reused PIDs.
- Independent identity-boundary repro (4 cases) GREEN; extra MI/prefix/audio/bijection tests added.

## Prior on PR #26 (`146d04c`)

- Replace invalid `Dispatch('SystemDeviceEnum')` with typed COM `ICreateDevEnum`.
- Enumerate video capture category only; DevicePath trust; HF3 candidate script.
