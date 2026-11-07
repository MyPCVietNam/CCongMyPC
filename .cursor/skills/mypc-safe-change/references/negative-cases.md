# Minimum adversarial matrix for PR reviews

## Windows process manager
- PID reused with different CreationDate -> refuse; blank CreationDate -> refuse.
- `uvicorn` on the right port but wrong `--app-dir` -> refuse, even if HF3 path occurs in `--log-config`.
- One `python.exe` descendant with correct full process ancestry and metadata -> potentially valid, but only with listener match and health READY.
- `conhost.exe`, foreign Python, wrong session, multiple listeners, stale owner metadata -> refuse; never kill.
- Synthetic test must mock the process termination boundary, not simply inject a fake WMI object while leaving `Stop-Process` real.
- Start failing health should clean up only verified own child/launcher processes. Stop returning false must not be reported as success.

## Camera/COM
- `CoInitializeEx` correct version-specific wrapper signature.
- DirectShow property read `VARIANT(VT_BSTR)` direct; two non-target monikers may have missing DevicePath; unique target still requires exact identity.
- PnP ↔ DevicePath: reject prefix-overlap, different MI, similar serial/instance, audio sibling, duplicate friendly name, re-enumeration reorder, no path, two possible matches.
- No frame means no physical pass even if enumeration and mapping succeeded.

## Data/security
- Legacy and partial evidence cannot sign new camera physical gate; disable/MOCK and credential changes must follow trust-revocation policy.
- API mutations require auth/CSRF; SQLite/biometric/HMAC and owner identifiers never enter public ZIP; rollback preserves DataDir.
