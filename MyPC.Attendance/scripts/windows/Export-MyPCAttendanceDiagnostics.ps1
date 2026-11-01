#Requires -Version 5.1
<#
.SYNOPSIS
  Xuất gói chẩn đoán đã làm sạch — không gồm mật khẩu, embedding, ảnh sinh trắc, DB đầy đủ.
#>
param(
  [string]$DataDir = (Join-Path $env:ProgramData "MyPC\Attendance\data"),
  [string]$OutDir = (Join-Path $env:ProgramData "MyPC\Attendance\diagnostics")
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$bundle = Join-Path $OutDir ("diagnostics-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Force -Path $bundle | Out-Null

$safe = [ordered]@{
  exported_at       = (Get-Date).ToString("o")
  windows           = [System.Environment]::OSVersion.VersionString
  data_dir_exists   = (Test-Path $DataDir)
  camera_lab_pass   = $false
  note_vi           = "Gói chẩn đoán KHÔNG gồm mật khẩu camera, face/body ciphertext, FIRST_RUN_ADMIN.txt, progress_json nhạy cảm hay DB đầy đủ."
  forbidden_copied  = @("*.key", "*secret*", "*FIRST_RUN*", "*.sqlite3", "*embedding*", "*password*")
}
$safe | ConvertTo-Json | Set-Content (Join-Path $bundle "summary.json") -Encoding UTF8

Get-ChildItem -Path $DataDir -Filter "*.log" -ErrorAction SilentlyContinue |
  Copy-Item -Destination $bundle -ErrorAction SilentlyContinue

# Never copy secrets/
$secrets = Join-Path $DataDir "secrets"
if (Test-Path $secrets) {
  Set-Content (Join-Path $bundle "secrets-PRESENT-redacted.txt") "Thư mục secrets tồn tại — không sao chép." -Encoding UTF8
}

Compress-Archive -Path (Join-Path $bundle "*") -DestinationPath ($bundle + ".zip") -Force
Write-Host "Đã xuất: $bundle.zip" -ForegroundColor Green
Write-Host "Kiểm tra nội dung ZIP trước khi gửi — không được có mật khẩu/embedding." -ForegroundColor Yellow
