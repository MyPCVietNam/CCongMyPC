# P02R Windows Lab

## Delivered (lab-ready, not executed on owner PC by this agent)

- `scripts/windows/Readiness-PR8.ps1` — read-only preflight (VI messages)
- `scripts/windows/Invoke-MyPCLabRun.ps1` — localhost lab-run FSM helper (no RTSP secrets)
- `scripts/windows/Invoke-MyPCCameraDiagnostics.ps1` / `Test-MyPCCamera.ps1` / `Start-MyPCAttendance.ps1` (PYTHONPATH start)
- `docs/vi/HUONG_DAN_KIEM_CAMERA_WINDOWS.md` — Vietnamese operator guide
- `docs/WINDOWS_OWNER_CHECKLIST.md` — from PR8 handoff

## Gate status

| Gate | Status |
|------|--------|
| WIN01 readiness scripts | PASS (scripts present; Cloud cannot run Win32) |
| WIN02 company LAN camera | **BLOCKED** |
| WIN03 consented face pilot | **BLOCKED** |
| WIN04 installer | **BLOCKED** / NOT_RUN |

Owner action: follow `docs/vi/HUONG_DAN_KIEM_CAMERA_WINDOWS.md` on Windows 10/11 x64 LAN.
