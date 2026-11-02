#Requires -Version 5.1
<#
.SYNOPSIS
  Khởi động MyPC Attendance trên Windows (local/offline lab hoặc production local).
.NOTES
  Không nhúng mật khẩu camera vào tham số dòng lệnh.
  PowerShell launcher ≠ bộ cài .exe đã kiểm chứng (INSTALLER vẫn BLOCKED).
  Dùng npm.cmd (không npm.ps1) để tránh ExecutionPolicy.
  File này UTF-8 BOM — tương thích Windows PowerShell 5.1.
#>
param(
  [string]$Root = (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent),
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8765,
  [ValidateSet("production", "development", "demo")]
  [string]$AppEnv = "production",
  [switch]$DemoMode,
  [switch]$AllowSyntheticFixtures,
  [string]$DataDir = ""
)

$ErrorActionPreference = "Stop"
$Backend = Join-Path $Root "backend"
$ReqRuntime = Join-Path $Backend "requirements.txt"
$ReqDev = Join-Path $Backend "requirements-dev.txt"
if (-not $DataDir) {
  $DataDir = Join-Path $env:ProgramData "MyPC\Attendance\data"
}
$ModelsDir = Join-Path $Root "models\weights"
$FrontendDist = Join-Path $Backend "app\static\index.html"
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

Write-Host "startup_phase=STARTING data_dir=$DataDir" -ForegroundColor DarkCyan

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  Write-Host "Chưa có .venv. Tạo bằng:" -ForegroundColor Yellow
  Write-Host "  py -3.12 -m venv .venv" -ForegroundColor Yellow
  Write-Host "  .\.venv\Scripts\python.exe -m pip install -U pip" -ForegroundColor Yellow
  Write-Host "  .\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt" -ForegroundColor Yellow
  Write-Host "  (runtime-only: -r backend\requirements.txt)" -ForegroundColor Yellow
  Write-Host "Chỉ cài khi bạn chủ động đồng ý — script không tự tải binary lạ." -ForegroundColor Yellow
  Write-Host "Dùng npm.cmd ci / npm.cmd run build trong thư mục frontend (không cần đổi ExecutionPolicy)." -ForegroundColor Yellow
  exit 1
}

if (-not (Test-Path $ReqRuntime)) {
  Write-Host "Thiếu backend\requirements.txt — kiểm tra thư mục MyPC.Attendance." -ForegroundColor Red
  exit 2
}

Write-Host "Kiểm tra model SHA256 (nếu có weights)..." -ForegroundColor DarkCyan
$Manifest = Join-Path $Root "models\manifest.json"
if (Test-Path $Manifest) {
  Write-Host "  Có manifest: $Manifest — ứng dụng sẽ xác minh khi tải YuNet/SFace." -ForegroundColor DarkCyan
} else {
  Write-Host "  Thiếu manifest — REAL model có thể NOT_READY." -ForegroundColor Yellow
}

if (-not (Test-Path $FrontendDist)) {
  Write-Host "Chưa có UI build (backend\app\static). Chạy:" -ForegroundColor Yellow
  Write-Host "  cd frontend" -ForegroundColor Yellow
  Write-Host "  npm.cmd ci" -ForegroundColor Yellow
  Write-Host "  npm.cmd run build" -ForegroundColor Yellow
}

$profiles = @(
  (Join-Path $env:LOCALAPPDATA "MyPC\Attendance\data"),
  (Join-Path $env:ProgramData "MyPC\Attendance\data"),
  (Join-Path $Root "data")
)
$existing = @()
foreach ($p in $profiles) {
  if (Test-Path (Join-Path $p "mypc_attendance.sqlite3")) { $existing += $p }
}
if ($existing.Count -gt 1 -and -not $env:MYPC_DATA_DIR) {
  Write-Host "CẢNH BÁO: nhiều hồ sơ SQLite tồn tại. Đang dùng: $DataDir" -ForegroundColor Yellow
  foreach ($p in $existing) { Write-Host "  - $p" -ForegroundColor Yellow }
  Write-Host "Đặt -DataDir hoặc MYPC_DATA_DIR rõ ràng; KHÔNG gộp/ghi đè DB." -ForegroundColor Yellow
}

$env:MYPC_DATA_DIR = $DataDir
$env:MYPC_MODELS_DIR = $ModelsDir
$env:MYPC_APP_ENV = $AppEnv
$env:MYPC_ALLOW_SYNTHETIC_FIXTURES = "false"
$env:MYPC_ALLOW_FORCE_SLOT = "false"
if ($DemoMode) {
  $env:MYPC_DEMO_MODE = "true"
  $env:MYPC_ALLOW_MOCK_OBSERVATION = "true"
  $env:MYPC_APP_ENV = "demo"
}
if ($AllowSyntheticFixtures -and $AppEnv -ne "production") {
  $env:MYPC_ALLOW_SYNTHETIC_FIXTURES = "true"
  $env:MYPC_ALLOW_FORCE_SLOT = "true"
  Write-Host "CẢNH BÁO: Đã bật fixture tổng hợp — không dùng cho production." -ForegroundColor Yellow
}

try {
  & $VenvPython -c "import cv2; assert hasattr(cv2,'FaceDetectorYN') and hasattr(cv2,'FaceRecognizerSF')"
  if ($LASTEXITCODE -ne 0) {
    Write-Host "OpenCV chưa sẵn sàng. Cài: .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt" -ForegroundColor Yellow
  }
} catch {
  Write-Host "OpenCV smoke thất bại — kiểm tra backend\requirements.txt (opencv-contrib-python-headless)." -ForegroundColor Yellow
}

Write-Host "startup_phase=MIGRATING_THEN_LISTEN http://$HostAddress`:$Port" -ForegroundColor Cyan
Write-Host "Môi trường: $env:MYPC_APP_ENV | DemoMode=$DemoMode | bind mặc định localhost" -ForegroundColor DarkCyan
Write-Host "Nếu console yên sau Alembic: kiểm tra /api/v1/health (startup_phase) — không kết luận treo." -ForegroundColor DarkCyan
Write-Host "LAN chỉ bật khi cấu hình tường lửa + HTTPS + xác thực (không mở go2rtc ra LAN)." -ForegroundColor DarkCyan
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$Backend;$env:PYTHONPATH" } else { $Backend }
& $VenvPython -m uvicorn app.main:app --host $HostAddress --port $Port
exit $LASTEXITCODE
