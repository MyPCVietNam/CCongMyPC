# P02-USB-HF3 architecture decisions

1. **Typed COM only.** System Device Enumerator via `CoCreateInstance` + `ICreateDevEnum`. Never ProgID Dispatch.
2. **DevicePath is identity; FriendlyName is UI.** OpenCV CAP_DSHOW index is the VideoInputDeviceCategory ordinal after proven DevicePath↔PnP match — ephemeral.
3. **Audio functions excluded** from WMI video candidates (microphone / *Audio* / Media class).
4. **Trust stages unchanged in spirit:** PNP_ID_FOUND → CAPTURE_MAPPING_VERIFIED (DevicePath) → OPENED → FRAME_RECEIVED.
5. **Candidate isolation:** HF3 DataDir under `p02-usb-hf3-candidate`, port 18878 only.
6. **comtypes ownership:** never manual `Release()` on owned pointers; drop Python refs before `CoUninitialize` on the STA worker; finalize release-warning telemetry after cleanup.
7. **Update rename:** PowerShell 5.1 `Rename-Item -NewName` is a same-parent leaf only; stage+validate before swap; rollback on failure.
8. **CoInitializeEx:** call comtypes 1.4.17 wrapper as `CoInitializeEx(flags)` only; apartment-init failures use `DSHOW_COINIT_FAILED` (never mislabel as CoCreate).
9. **IPropertyBag.Read:** request `VT_BSTR` and pass the VARIANT instance directly; never byref-first or TypeError fallback. Absent DevicePath (`0x80070002`) leaves that moniker unverified only.
10. **PID ownership:** venv `Start-Process` PID may be a redirector; accept DirectShow uvicorn listener only as DIRECT or VERIFIED_DESCENDANT python with exact cmdline + creation-time meta. Never trust HTTP 200 alone; never kill foreign 18878 owners.
