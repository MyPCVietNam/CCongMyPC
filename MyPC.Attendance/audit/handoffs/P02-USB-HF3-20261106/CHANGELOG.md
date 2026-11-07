# P02-USB-HF3 changelog

## Patch on PR #27 — CoInitializeEx(flags) signature (in-place)

- Fix `CoInitializeEx(_COINIT_APARTMENTTHREADED)` for comtypes 1.4.17 (one arg).
- Classify init failures as `DSHOW_COINIT_FAILED` (not `DSHOW_COCREATE_FAILED`).
- Independent repro: `tests/unit/test_p02_usb_hf3_coinit_signature.py`.
- Owner Windows STA init/bag guard extended (still SKIP in CI without flag).

## Prior — COM exactly-once release + PS5.1 Update

- No manual `Release()` on comtypes-owned pointers; warning count after cleanup.
- Update leaf Rename-Item + rollback + port guard.

## Prior — IPropertyBag + identity

- STA worker, CreateBindCtx, BindToStorage stage telemetry.
- Strict VID+PID+MI+instance + 1:1 bijection retained.
