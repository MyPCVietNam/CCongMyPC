# P02-USB-HF3 — IPropertyBag VT_BSTR direct Read RCA (PR #27 in-place)

**Pre-fix PR #27 tip (this corrective):** `aa0c385f414d410d2c6aa0cdec7d676fb8f2ac7e`

**Prior CoInit freeze:** `bd8aaf08651d2039a5e3a25f6ea7b88f1adf95f0`

## Owner Windows session-only probe (2026-11-07)

In-memory adapters only (disk source edited=false; frames=false; HMAC=false):

- `DSHOW_ENUM_OK=true`, monikers=3, bag bind=3
- FriendlyName: original/byref **0/3** HRESULT `0x80070057`; **VT_BSTR + direct VARIANT 3/3**
- DevicePath: **VT_BSTR + direct 1/3**; other rows `0x80070002` (property absent)
- With direct read: canonical=1, verified pair=1, `CAPTURE_MAPPING_VERIFIED=true` (diagnostic only)
- `COM_RELEASE_WARNING_COUNT=0`

Does **not** certify streaming, 1080p, soak, biometrics, or CAMERA_LAB.

## Root cause

`_read_propbag_str` created `VARIANT()` (VT_EMPTY) and called `Read(..., byref(var), ...)` first,
with a silent TypeError→direct fallback that never ran on Windows (COMError, not TypeError).

## Fix

1. `var.vt = VT_BSTR`; `prop_bag.Read(name, var, None)` — VARIANT instance, never byref.
2. No TypeError byref fallback.
3. Classify `0x80070002` / `FileNotFoundError` as `DSHOW_DEVICE_PATH_MISSING` on that moniker
   (unverified); do not poison a unique matched target.
4. Keep CoInit one-arg, STA worker, exactly-once Release, post-cleanup warning count.
5. Strict VID/PID/MI/full-instance identity unchanged.

Physical / soak / CAMERA_LAB / FACE_PILOT / installer / production remain **BLOCKED**.
