# P02-USB-HF3 changelog

## Patch on PR #27 — IPropertyBag VT_BSTR direct VARIANT (in-place)

- `_read_propbag_str`: set `VT_BSTR`, pass VARIANT instance directly (not byref).
- No TypeError→byref fallback.
- Missing DevicePath (`0x80070002`) on non-target monikers → unverified row only.
- Independent repro: `tests/unit/test_p02_usb_hf3_owner_vtbstr_direct.py`.

## Prior — CoInitializeEx(flags) signature

- One-arg `CoInitializeEx(_COINIT_APARTMENTTHREADED)`; `DSHOW_COINIT_FAILED`.

## Prior — COM exactly-once release + PS5.1 Update

- No manual Release; warning count after cleanup; leaf Rename-Item + rollback.

## Prior — identity / IPropertyBag stages

- Strict VID+PID+MI+instance + 1:1 bijection retained.
