#Requires -Version 5.1
param([int]$Port = 8765)
$ErrorActionPreference = "SilentlyContinue"
Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Write-Host "Đã yêu cầu dừng tiến trình lắng nghe cổng $Port." -ForegroundColor Cyan
