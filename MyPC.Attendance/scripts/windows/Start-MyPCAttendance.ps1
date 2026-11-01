#Requires -Version 5.1
<#
.SYNOPSIS
  Khởi động MyPC Attendance trên Windows (chế độ local/offline).
.NOTES
  Không nhúng mật khẩu camera vào tham số dòng lệnh.
#>
param(
  [string]$Root = (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent),
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8765,
  [ValidateSet("production", "development", "demo")]
  [string]$AppEnv = "production",
  [switch]$DemoMode
)

$ErrorActionPreference = "Stop"
$Backend = Join-Path $Root "backend"
$DataDir = Join-Path $env:ProgramData "MyPC\Attendance\data"
$ModelsDir = Join-Path $Root "models\weights"
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  Write-Host "Chưa có .venv. Tạo môi trường và cài dependency trước (xem docs/vi/windows-camera-lab.md)." -ForegroundColor Yellow
  exit 1
}

$env:MYPC_DATA_DIR = $DataDir
$env:MYPC_MODELS_DIR = $ModelsDir
$env:MYPC_APP_ENV = $AppEnv
if ($DemoMode) {
  $env:MYPC_DEMO_MODE = "true"
  $env:MYPC_ALLOW_MOCK_OBSERVATION = "true"
  $env:MYPC_APP_ENV = "demo"
}

Write-Host "Khởi động MyPC Attendance tại http://$HostAddress`:$Port ..." -ForegroundColor Cyan
Write-Host "Môi trường: $env:MYPC_APP_ENV | DemoMode=$DemoMode" -ForegroundColor DarkCyan
& $VenvPython -m uvicorn app.main:app --app-dir $Backend --host $HostAddress --port $Port
