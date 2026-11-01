#Requires -Version 5.1
param(
  [string]$DataDir = (Join-Path $env:ProgramData "MyPC\Attendance\data"),
  [string]$OutDir = (Join-Path $env:TEMP "MyPCAttendance-Diagnostics")
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$bundle = Join-Path $OutDir ("diagnostics-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Force -Path $bundle | Out-Null

$safe = [ordered]@{
  exported_at = (Get-Date).ToString("o")
  windows     = [System.Environment]::OSVersion.VersionString
  data_dir_exists = (Test-Path $DataDir)
  note_vi = "Gói chẩn đoán KHÔNG gồm mật khẩu camera, face template, FIRST_RUN_ADMIN.txt hay DB đầy đủ."
}
$safe | ConvertTo-Json | Set-Content (Join-Path $bundle "summary.json") -Encoding UTF8

# Copy only non-secret logs if present
Get-ChildItem -Path $DataDir -Filter "*.log" -ErrorAction SilentlyContinue |
  Copy-Item -Destination $bundle -ErrorAction SilentlyContinue

Write-Host "Đã xuất: $bundle" -ForegroundColor Green
