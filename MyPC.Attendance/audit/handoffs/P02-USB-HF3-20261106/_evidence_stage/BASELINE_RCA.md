# P02-USB-HF3 — CoInitializeEx signature RCA (PR #27 in-place)

**Pre-fix PR #27 tip (this corrective):** `98d8d40290018d688749931a9f78d4ee016b126b`

**Prior COM-release freeze:** `e0ad4aaca25bcbdeb8777bc6b509a518c97db1d2`

## Owner Windows (2026-11-07)

- Update SUCCESS; Preflight SUCCESS; PnP video=1; MODEL_PINS_PASS=true.
- `DSHOW_ENUM_OK=false`, moniker count=0.
- `DSHOW_BLOCKER_CODE=DSHOW_COCREATE_FAILED`, `FIRST_EXCEPTION_CLASS=TypeError`.
- `stage_notes=["coinit:TypeError"]`, `COM_RELEASE_WARNING_COUNT=0` (early failure — **not** physical PASS).

## Root cause (verified vs comtypes 1.4.17)

Production called `CoInitializeEx(None, _COINIT_APARTMENTTHREADED)` (two args).

Official wrapper:

```python
def CoInitializeEx(flags=None):
    ...
    _CoInitializeEx(None, flags)
```

Two-arg call → Python `TypeError` before any CoCreateInstance; mislabeled as `DSHOW_COCREATE_FAILED`.

## Fix

1. `CoInitializeEx(_COINIT_APARTMENTTHREADED)` — one flags argument.
2. New blocker `DSHOW_COINIT_FAILED` for apartment-init failures (distinct from CoCreate).
3. Keep exactly-once comtypes Release ownership and post-cleanup warning telemetry.

Physical USB / CAMERA_LAB / FACE_PILOT / installer / production remain **BLOCKED**.
