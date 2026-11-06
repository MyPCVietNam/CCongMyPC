# P02-USB UVC gate matrix

| Gate ID | Class | Status | Evidence |
|---------|-------|--------|----------|
| CODE_FIX_USB_GATEWAY | code | CI | Fake-device unit/integration tests |
| CODE_FIX_USB_TRUST | code | CI | Material source_type/usb_stable_id revokes HMAC; ROI/name harmless |
| CODE_FIX_RTSP_REGRESSION | code | CI | Existing RTSP tests unchanged |
| USB_WINDOWS_PHYSICAL | physical | **BLOCKED** | Owner UGREEN enumerate + 1080p MJPG |
| USB_STABILITY_30_MIN | physical | **BLOCKED** | Owner soak |
| USB_CAMERA_LAB_OWNER_SIGN | physical+HMAC | **BLOCKED** | USB-bound lab; no EZVIZ inherit |
| FACE_PILOT | physical+HMAC | **BLOCKED** | Not enabled by USB connect |
| INSTALLER | release | **BLOCKED** | — |
| PRODUCTION_READY | release | **BLOCKED** | — |

Never claim physical PASS unless owner executed on Windows with the real UGREEN device.
