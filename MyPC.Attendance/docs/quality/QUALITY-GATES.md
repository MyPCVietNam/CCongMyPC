# MyPC Quality Gates v1.0 — binding contract

This is not an installer and does not approve owner hardware. It is a repository-level quality framework.

| Gate | Evidence for PASS | Explicitly insufficient |
|---|---|---|
| `GUARD_FRAMEWORK` | Rules/hooks syntax, hook unit tests, archive-verifier tests | Agent prose |
| `BACKEND_CI` | GitHub check `backend-linux` on exact HEAD | Local Cursor pytest summary |
| `FRONTEND_CI` | GitHub check `frontend` on exact HEAD | Screenshot/build directory alone |
| `WINDOWS_CODE` | GitHub `windows-contract` using PowerShell 5.1, parse/PSA/Pester and pure Python | Linux pytest; PS7 only |
| `PID_SAFETY` | Negative tests for wrong --app-dir, PID reuse, absent creation, fake-PID isolation, no real Stop-Process in tests | A synthetic WMI object paired with live Stop-Process |
| `USB_ENUM_MAPPING` | Owner Diagnose with 1:1 PnP↔DirectShow full identity, COM warnings zero | Friendly name, index, or model pins alone |
| `USB_WINDOWS_PHYSICAL` | Owner actually captures correct UGREEN frame with measured WxH/FPS, frame evidence kept locally | backend health / COM enumeration |
| `USB_STABILITY_30_MIN` | Owner 30-minute real camera soak report | Single screenshot / mock loop |
| `USB_CAMERA_LAB_OWNER_SIGN` | Explicit signed owner evidence bound to USB subject and revision | Previous EZVIZ HMAC, CI or mock |
| `FACE_PILOT`, `INSTALLER`, `PRODUCTION_READY` | Their own approved Windows/owner gates | Any preceding gate by itself |

Block merge when an expected CI check is missing, skipped, timed out, stale or failed. In a repository where `main` is only LICENSE, add the workflow to the active source-carrying PR branch first; a green status against the LICENSE-only tree means nothing about Attendance.

## Baseline RED -> feature GREEN

- Record the bug and baseline commit, plus exact reproducible negative test.
- Demonstrate failure for the right reason at baseline.
- Implement minimal fix; verify all existing relevant tests and negative test green.
- Require independent diff review. Don't dilute assertions, mock incorrectly or whitelist the bug.

## Windows physical validation

Only the owner may run start/stop/capture against the local candidate. Never run these commands as part of GitHub CI or agent-provided auto-install. Keep `18876`, `18877` and their HMAC/DataDir untouched. USB staging is `18878` only. Make the owner's explicit decision a separate step after code gates pass.
