# P02-USB-HF2 architecture decisions

1. **Trust stages are ordered and fail-closed.** Only `CAPTURE_MAPPING_VERIFIED` (unique hashed PnP ↔ unique DirectShow index) enables trusted LIVE / CAMERA_LAB physical eligibility. `PNP_ID_FOUND` alone is insufficient. `OPENED` / `FRAME_RECEIVED` are runtime evidence, not identity proof.

2. **OpenCV CAP_DSHOW is index-only.** Named FFmpeg `video=` strings are rejected. Windows enumeration uses COM/WMI via pinned `requirements-windows.txt`; absence → honest failure, not fabricated opens.

3. **Gateway identity re-resolve clears stale index first.** Temporary disconnect does not forge a new subject; material USB identity or profile change rotates `config_revision` and revokes prior PHYSICAL/HMAC per existing lifecycle.

4. **Candidate isolation.** Port `18878` + separate DataDir + `MYPC_MODELS_DIR`. Never copy HF5/P02 secrets. Physical Start/Export verified only on owner Windows lab.
