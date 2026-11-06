# P02-USB-HF3 changelog

## Patch on PR #27 — COM exactly-once release + PS5.1 Update (in-place)

- Remove manual `Release()` on comtypes-owned pointers (finalizer owns exactly-once Release).
- Finalize `COM_RELEASE_WARNING_COUNT` after root pointer drops + `CoUninitialize`.
- Candidate `-Mode Update`: leaf-only `Rename-Item -NewName`, staged layout + SHA256 before swap,
  port 18878 guard, rollback on failure; never wipe DataDir/venv/models.
- Independent repro: `tests/unit/test_p02_usb_hf3_com_release_update.py` (was 3 FAIL → PASS).
- Fake-directory Update promote/rollback tests (no real candidate).

## Prior patch on PR #27 — IPropertyBag + COM lifetime (in-place)

- Dedicated STA COM worker thread for DirectShow enum (no pythoncom mix with WMI).
- CreateBindCtx + BindToStorage(IID_IPropertyBag) + stage telemetry.
- Truthful blockers when enum succeeds but property bags fail.
- Keep strict VID+PID+MI+instance identity + 1:1 bijection.

## Prior identity patch / native COM enum

See earlier CHANGELOG entries; strict matching retained.
