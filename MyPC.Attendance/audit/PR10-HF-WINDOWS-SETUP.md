# PR10-HF Windows Setup

## Clean install (Windows 10 22H2 / 11)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
.\scripts\windows\Start-MyPCAttendance.ps1 -DataDir "$env:ProgramData\MyPC\Attendance\data"
```

- Use **`npm.cmd`**, not `npm.ps1` (ExecutionPolicy).
- All shipped `.ps1` files are **UTF-8 with BOM** for Windows PowerShell 5.1.
- Requirements path is `backend\requirements.txt` / `backend\requirements-dev.txt`.
- OpenCV: exactly `opencv-contrib-python-headless==4.13.0.92` (do not also install `opencv-python*`).
- After Alembic quiet console: check `GET http://127.0.0.1:8765/api/v1/health` → `startup_phase=READY` (do not assume hang).

## Readiness

`.\scripts\windows\Readiness-PR10.ps1` — pin `f6719f0…`, TCP camera probe only, gates BLOCKED.

## Agent evidence

| Item | Result |
|------|--------|
| UTF-8 BOM on all `.ps1` | PASS (unit) |
| No Set-ExecutionPolicy | PASS (unit) |
| OpenCV FaceDetectorYN/SF | PASS (Linux venv 4.13.0) |
| Native PS 5.1/7 parse | BLOCKED (no Windows runner) |
| Installer | BLOCKED |
