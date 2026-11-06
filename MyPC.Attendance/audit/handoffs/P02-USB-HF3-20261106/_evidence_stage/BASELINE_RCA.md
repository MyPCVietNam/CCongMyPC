# P02-USB-HF3 — Root cause (baseline PR #26)

**Baseline:** `146d04cb930a446f891f48178a33672f0537b95e`

## Owner Windows evidence (2026-11-06)

- WMI found UGREEN video + related audio functions.
- `Dispatch('SystemDeviceEnum')` → `com_error` HRESULT `-2147221005` / `0x800401F3` (`CO_E_CLASSSTRING`).
- `DSHOW_MONIKER_COUNT=0` was enumerator failure, **not** proof camera absent.
- Prior CAP_DSHOW index 2 delivered real 1920x1080 — ephemeral, not stable identity.

## Defect

`usb_device._try_pywin32_dshow_names` used Automation ProgID Dispatch.  
`CLSID_SystemDeviceEnum` is native COM (`ICreateDevEnum`), not IDispatch.

## Fix

1. `dshow_com_enum.py`: `CoCreateInstance(CLSID_SystemDeviceEnum, ICreateDevEnum)` +
   `CreateClassEnumerator(CLSID_VideoInputDeviceCategory)`; read FriendlyName + **DevicePath**.
2. Map DevicePath ↔ PnP USB video function; exclude audio WMI entries.
3. CAPTURE_MAPPING_VERIFIED only with unique DevicePath fingerprint + ephemeral index.
4. HF3 candidate script + read-only redacted Diagnose; model pins via `models/manifest.json` array.
5. Never FFmpeg `video=Name` on CAP_DSHOW.

## Rollback

PR #26 tip `146d04c`. Do not mutate owner DataDirs / 18876 / 18877.
