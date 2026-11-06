# P02-USB-HF3 changelog

## Patch on PR #27 — IPropertyBag + COM lifetime (in-place)

- Dedicated STA COM worker thread for DirectShow enum (no pythoncom mix with WMI).
- CreateBindCtx + BindToStorage(IID_IPropertyBag) + explicit reverse-order Release before CoUninitialize.
- Per-stage redacted counters: PROPERTY_BAG_BIND_OK / FRIENDLY_NAME_READ / DEVICE_PATH_READ / CANONICAL / COM_RELEASE_WARNING.
- Truthful blockers when enum succeeds but property bags fail (no silent empty success).
- Candidate `-Mode Update` refreshes source without wiping DataDir/venv/models.
- Keep strict VID+PID+MI+instance identity + 1:1 bijection.

## Prior identity patch / native COM enum

See earlier CHANGELOG entries; strict matching retained.
