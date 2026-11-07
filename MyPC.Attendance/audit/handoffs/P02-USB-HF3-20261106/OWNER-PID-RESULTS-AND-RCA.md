# Owner evidence and interpretation - HF3 PID owner investigation

Date: 2026-11-07 (Asia/Bangkok). Target: isolated MyPC Attendance HF3, 127.0.0.1:18878. PR #27 last observed HEAD: 2fcb5bf05cd61d47be93cbfbbbbb62ec4e16bddc.

## Verified Windows output

- Existing candidate Update PASS, Preflight PASS, USB Diagnose exit 0.
- DSHOW_ENUM_OK=true; DSHOW_VIDEO_MONIKER_COUNT=3; PROPERTY_BAG_BIND_OK_COUNT=3; FRIENDLY_NAME_READ_OK_COUNT=3; DEVICE_PATH_READ_OK_COUNT=1; VIDEO_DEVICE_PATH_MATCH_COUNT=1; CAPTURE_MAPPING_VERIFIED=true; COM_RELEASE_WARNING_COUNT=0; MODEL_PINS_PASS=true.
- OpenCV 4.13.0: CAP_DSHOW_AVAILABLE=True; CAP_MSMF_AVAILABLE=False.
- -Mode Start: Start-Process returned PID 24776. GET /api/v1/health returned HTTP 200, but listener PID was NOT 24776. Start aborted with ownership error, then generic health failure. No frames captured.
- Subsequent independent venv Python no-network/no-camera read-only test:

  LISTENERS=0
  LauncherPid=26272; LauncherName=python
  DirectChildCount=2
  ChildPid=10220,5152
  ChildName=conhost.exe,python.exe
  RedirectorChildObserved=True
  PID_PROBE_DONE: no process was stopped and no candidate files were changed.

## What this demonstrates

The Windows Python 3.12 venv python.exe spawned a direct python.exe child under this independent probe. This is strong evidence for why equating launcher PID with listening server PID is unreliable on this host. The conhost.exe child is not a Uvicorn server and MUST NOT be treated as one. Because LISTENERS=0 when the probe ran, the original unknown 18878 listening PID was NOT positively linked to prior launcher 24776. The implementation MUST verify ownership rather than make that assumption.

## Desired outcome

Correct candidate-owned listener detection and process lifetime management without relaxing host/port verification, without killing foreign processes, and without touching existing 18876/18877, DataDir, venv, ONNX weights, HMAC, USB strict matching or physical gates.

All gates for camera frame capture, 30-minute soak and signed owner evidence remain BLOCKED.
