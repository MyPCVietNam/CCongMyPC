#Requires -Version 5.1
<#
.SYNOPSIS
  DEPRECATED (P02S): không dùng cookie/CSRF/challenge trên dòng lệnh.
.DESCRIPTION
  Dùng trang Windows Lab trong UI đã đăng nhập (http://127.0.0.1:8765/lab-windows).
  Script này cố ý thoát lỗi để tránh lộ session token trong lịch sử PowerShell.
#>
param()
$ErrorActionPreference = 'Stop'
Write-Host 'P02S: Invoke-MyPCLabRun.ps1 đã ngừng nhận token phiên / CSRF / challenge trên CLI.' -ForegroundColor Yellow
Write-Host 'Mở http://127.0.0.1:8765/lab-windows sau khi đăng nhập trên máy Windows LAN.' -ForegroundColor Cyan
Write-Host 'Preflight an toàn: .\scripts\windows\Readiness-PR9.ps1' -ForegroundColor Cyan
Write-Host 'CAMERA_LAB / FACE_PILOT vẫn BLOCKED cho đến khi có bằng chứng vật lý thật.' -ForegroundColor DarkYellow
exit 2
