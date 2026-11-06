# P02-USB-HF3 — Property bag / COM lifetime RCA

**Pre-fix PR #27 tip:** `05f6ba991b4b43b3719125551298b18441578bcb`

## Owner Windows (2026-11-06)

- DSHOW moniker count=3, PnP video=1, but ALL FriendlyName/DevicePath empty.
- Diagnose exit 2; three Win32 IUnknown release exceptions at process exit.
- COM ProgID blocker already gone; failure is the **property-bag stage**, not enumeration.

## Likely defects addressed

1. Mixing `pythoncom.CoInitialize/CoUninitialize` on the caller thread with comtypes objects while WMI may still hold live IUnknowns → release exceptions / unstable BindToStorage.
2. Swallowed BindToStorage/Read exceptions treated as empty success; aggregate blocker stayed empty.
3. Missing CreateBindCtx and explicit reverse-order Release before CoUninitialize.

## Fix

Dedicated STA worker + CreateBindCtx + stage telemetry + Update mode for prepared candidates.

Strict identity matching unchanged. Physical USB still BLOCKED until owner Diagnose shows bag/path reads.
