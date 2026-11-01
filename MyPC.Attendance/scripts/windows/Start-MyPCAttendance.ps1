#Requires -Version 5.1
<#
.SYNOPSIS
  Khởi động MyPC Attendance trên Windows (local/offline lab hoặc production local).
.NOTES
  Không nhúng mật khẩu camera vào tham số dòng lệnh.
  PowerShell launcher ≠ bộ cài .exe đã kiểm chứng (INSTALLER vẫn BLOCKED).
#>
param(
  [string]$Root = (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent),
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8765,
  [ValidateSet("production", "development", "demo")]
  [string]$AppEnv = "production",
  [switch]$DemoMode,
  [switch]$AllowSyntheticFixtures
)

$ErrorActionPreference = "Stop"
$Backend = Join-Path $Root "backend"
$DataDir = Join-Path $env:ProgramData "MyPC\Attendance\data"
$ModelsDir = Join-Path $Root "models\weights"
$FrontendDist = Join-Path $Backend "app\static\index.html"
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  Write-Host "Chưa có .venv. Tạo bằng:" -ForegroundColor Yellow
  Write-Host "  py -3.12 -m venv .venv" -ForegroundColor Yellow
  Write-Host "  .\.venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
  Write-Host "Chỉ cài khi bạn chủ động đồng ý — script không tự tải binary lạ." -ForegroundColor Yellow
  exit 1
}

Write-Host "Kiểm tra model SHA256 (nếu có weights)..." -ForegroundColor DarkCyan
$Manifest = Join-Path $Root "models\manifest.json"
if (Test-Path $Manifest) {
  Write-Host "  Có manifest: $Manifest — ứng dụng sẽ xác minh khi tải YuNet/SFace." -ForegroundColor DarkCyan
} else {
  Write-Host "  Thiếu manifest — REAL model có thể NOT_READY." -ForegroundColor Yellow
}

if (-not (Test-Path $FrontendDist)) {
  Write-Host "Chưa có UI build (backend/app/static). Chạy: cd frontend; npm ci; npm run build" -ForegroundColor Yellow
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

Write-Host "Khởi động MyPC Attendance tại http://$HostAddress`:$Port ..." -ForegroundColor Cyan
Write-Host "Môi trường: $env:MYPC_APP_ENV | DemoMode=$DemoMode | bind mặc định localhost" -ForegroundColor DarkCyan
Write-Host "LAN chỉ bật khi cấu hình tường lửa + HTTPS + xác thực (không mở go2rtc ra LAN)." -ForegroundColor DarkCyan
& $VenvPython -m uvicorn app.main:app --app-dir $Backend --host $HostAddress --port $Port
