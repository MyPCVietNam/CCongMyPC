#Requires -Version 5.1
<#
.SYNOPSIS
  Owner-only Windows USB UVC physical checks for MyPC Attendance P02-USB.
  Does NOT talk to 18876/18877. Does NOT paste secrets. BLOCKED until owner runs.

.NOTES
  Run against candidate http://127.0.0.1:18878 with isolated DataDir.
  Outputs redacted JSON under OutDir — no frames, no embeddings, no cookies.
#>
param(
  [string]$BaseUrl = "http://127.0.0.1:18878",
  [string]$OutDir = "$env:TEMP\mypc-p02-usb-physical",
  [switch]$Soak30Min
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$log = Join-Path $OutDir "physical-$stamp.jsonl"

function Write-Gate([string]$Name, [string]$Status, [string]$Note) {
  $row = [ordered]@{
    gate = $Name
    status = $Status
    note = $Note
    utc = (Get-Date).ToUniversalTime().ToString("o")
  }
  ($row | ConvertTo-Json -Compress) | Add-Content -Path $log -Encoding UTF8
  Write-Host "$Name = $Status :: $Note"
}

Write-Gate "USB_WINDOWS_PHYSICAL" "BLOCKED" "Script started — owner must complete steps manually with UGREEN attached."
Write-Gate "PREFLIGHT_PORT" "INFO" "Expect BaseUrl=$BaseUrl (not 18876/18877)."

Write-Host @"

Owner checklist (manual):
  1) Login locally at $BaseUrl — do not paste CSRF/cookies here.
  2) Camera → USB (Windows UVC) → Liệt kê USB → chọn UGREEN.
  3) Đo chế độ — record actual WxH/FOURCC (not set()).
  4) Gắn USB LIVE; open two MJPEG tabs; confirm one capture loop.
  5) Unplug/replug; confirm same stable_id; index reorder fail-closed if identity lost.
  6) Optional -Soak30Min: leave LIVE running 30 minutes; record CPU/FPS yourself.

"@

if ($Soak30Min) {
  Write-Gate "USB_STABILITY_30_MIN" "BLOCKED" "Soak flag set — owner must observe 30 minutes and mark PASS offline."
} else {
  Write-Gate "USB_STABILITY_30_MIN" "BLOCKED" "Not requested this run."
}

Write-Gate "USB_CAMERA_LAB_OWNER_SIGN" "BLOCKED" "Requires PHYSICAL_VERIFIED lab FSM + HMAC on USB subject — never inherit EZVIZ."
Write-Gate "FACE_PILOT" "BLOCKED" "Out of scope for connect/overlay alone."
Write-Host "Log: $log"
