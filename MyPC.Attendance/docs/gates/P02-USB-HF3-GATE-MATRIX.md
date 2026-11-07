# P02-USB-HF3 gate matrix

| Gate | Class | Status |
|------|-------|--------|
| CODE_FIX_NO_PROGID_SYSTEMDEVICEENUM | code | CI |
| CODE_FIX_VIDEO_DEVICEPATH_MAPPING | code | CI |
| CODE_FIX_AUDIO_EXCLUDED | code | CI |
| CODE_FIX_CANDIDATE_HF3_SCRIPT | code (contract) | CI — physical Start BLOCKED until owner Windows |
| CODE_FIX_PID_SAFETY_STOP_UPDATE | code (contract) | CI static GREEN; Windows PS 5.1 runtime owner-gated |
| CODE_FIX_PID_SAFETY_V3_HARNESS_APPDIR | code (contract) | V3 static 6 GREEN; mocked Stop-Process by default |
| USB_WINDOWS_PHYSICAL | physical | BLOCKED |
| USB_STABILITY_30_MIN | physical | BLOCKED |
| USB_CAMERA_LAB_OWNER_SIGN | physical+HMAC | BLOCKED |
| FACE_PILOT / INSTALLER / PRODUCTION_READY | release | BLOCKED |
