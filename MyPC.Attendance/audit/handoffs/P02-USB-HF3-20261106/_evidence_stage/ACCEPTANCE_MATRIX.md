# P02-USB-HF3 acceptance matrix

| ID | Criterion | Result |
|----|-----------|--------|
| A1 | ProgID SystemDeviceEnum absent; CoCreate ICreateDevEnum path present | CI PASS |
| A2 | Audio PnP excluded from video candidates | CI PASS |
| A3 | Unique DevicePath↔PnP → verified + ephemeral index | CI PASS |
| A4 | Missing DevicePath / name-only → unverified | CI PASS |
| A5 | PnP present / DShow empty → unverified | CI PASS |
| A6 | Duplicate names / ambiguous paths → fail closed | CI PASS |
| A7 | Index reorder same identity OK; wrong device rejected | CI PASS |
| A8 | HF3 script contract + model pin map; Start requires HTTP 200 | CI PASS |
| A9 | RTSP / FACE_PILOT gates unchanged | CI PASS |
| A10 | Independent identity-boundary (prefix / MI / wrong instance) | CI PASS (was 3/4 RED) |
| G-PHYS | USB_WINDOWS_PHYSICAL | **BLOCKED** until owner Diagnose |
| G-SOAK / LAB / FP / INST / PROD | physical/release | **BLOCKED** |
