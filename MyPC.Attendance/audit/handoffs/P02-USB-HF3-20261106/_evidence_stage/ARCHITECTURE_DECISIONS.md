# P02-USB-HF3 architecture decisions

1. **Typed COM only.** System Device Enumerator via `CoCreateInstance` + `ICreateDevEnum`. Never ProgID Dispatch.
2. **DevicePath is identity; FriendlyName is UI.** OpenCV CAP_DSHOW index is the VideoInputDeviceCategory ordinal after proven DevicePath↔PnP match — ephemeral.
3. **Audio functions excluded** from WMI video candidates (microphone / *Audio* / Media class).
4. **Trust stages unchanged in spirit:** PNP_ID_FOUND → CAPTURE_MAPPING_VERIFIED (DevicePath) → OPENED → FRAME_RECEIVED.
5. **Candidate isolation:** HF3 DataDir under `p02-usb-hf3-candidate`, port 18878 only.
