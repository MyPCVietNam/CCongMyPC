#Requires -Version 5.1
<#
.SYNOPSIS
  DEPRECATED (P02S): không nhận session cookie/CSRF trên CLI.
.DESCRIPTION
  Dùng trang Camera / Windows Lab trong UI đã đăng nhập để xem DECODED_MEASURED.
#>
param()
Write-Host 'P02S: Không truyền cookie/CSRF qua tham số PowerShell.' -ForegroundColor Yellow
Write-Host 'Đăng nhập UI localhost rồi dùng /camera hoặc /lab-windows.' -ForegroundColor Cyan
Write-Host 'Preflight: .\scripts\windows\Readiness-PR9.ps1' -ForegroundColor Cyan
exit 2
