#Requires -Version 5.1
<#
.SYNOPSIS
  Điều khiển lab-run CAMERA_LAB / FACE_PILOT qua API localhost (không nhận mật khẩu RTSP).
.DESCRIPTION
  Quy trình: start → measure → (face-cases) → owner-review → promote-physical.
  Không đánh CAMERA_LAB_PASS / FACE_PILOT_PASS; chỉ tạo evidence PHYSICAL_VERIFIED khi server đồng ý.
#>
param(
    [string]$BaseUrl = "http://127.0.0.1:8765",
    [Parameter(Mandatory = $true)][int]$CameraId,
    [Parameter(Mandatory = $true)][ValidateSet("CAMERA_LAB", "FACE_PILOT")][string]$Kind,
    [Parameter(Mandatory = $true)][string]$CsrfToken,
    [Parameter(Mandatory = $true)][string]$SessionCookie,
    [string]$OwnerChallenge = "",
    [ValidateSet("start", "measure", "owner-review", "promote", "status")]
    [string]$Step = "start",
    [string]$RunId = "",
    [string]$OutDir = (Join-Path $env:ProgramData "MyPC\Attendance\camera-lab")
)

$ErrorActionPreference = "Stop"
if ($BaseUrl -notmatch '^https?://(127\.0\.0\.1|localhost)(:\d+)?/?$') {
    Write-Error "Chỉ cho phép BaseUrl localhost/127.0.0.1 — từ chối $($BaseUrl)"
    exit 2
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$hdr = @{
    "X-CSRF-Token" = $CsrfToken
    "Cookie"       = ("mypc_session=" + $SessionCookie)
    "Content-Type" = "application/json"
}
$base = $BaseUrl.TrimEnd('/')
$result = $null
switch ($Step) {
    "start" {
        $result = Invoke-RestMethod -Method POST -Uri "$base/api/v1/cameras/$CameraId/lab-runs" `
            -Headers $hdr -Body (@{ kind = $Kind; profile = "MAIN" } | ConvertTo-Json)
        Write-Host "run_id=$($result.run_id) challenge=$($result.owner_challenge) state=$($result.state)"
    }
    "measure" {
        if (-not $RunId) { Write-Error "Cần -RunId"; exit 3 }
        $result = Invoke-RestMethod -Method POST -Uri "$base/api/v1/cameras/$CameraId/lab-runs/$RunId/measure" `
            -Headers $hdr -Body (@{ samples = 5 } | ConvertTo-Json)
        Write-Host "state=$($result.state) decoded=$($result.decoded_w)x$($result.decoded_h) fps=$($result.fps_measured)"
    }
    "owner-review" {
        if (-not $RunId) { Write-Error "Cần -RunId"; exit 3 }
        if (-not $OwnerChallenge) { Write-Error "Cần -OwnerChallenge từ bước start"; exit 4 }
        $result = Invoke-RestMethod -Method POST -Uri "$base/api/v1/cameras/$CameraId/lab-runs/$RunId/owner-review" `
            -Headers $hdr -Body (@{ challenge = $OwnerChallenge } | ConvertTo-Json)
        Write-Host "state=$($result.state)"
    }
    "promote" {
        if (-not $RunId) { Write-Error "Cần -RunId"; exit 3 }
        $result = Invoke-RestMethod -Method POST -Uri "$base/api/v1/cameras/$CameraId/lab-runs/$RunId/promote-physical" `
            -Headers $hdr -Body "{}"
        Write-Host "evidence_id=$($result.evidence_id) class=$($result.evidence_class) camera_lab_pass=$($result.camera_lab_pass)"
    }
    "status" {
        Write-Host "Dùng UI hoặc evidence API — không suy PASS từ health."
    }
}
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$out = Join-Path $OutDir ("lab-run-" + $Step + "-" + $stamp + ".json")
if ($null -ne $result) {
    ($result | ConvertTo-Json -Depth 8) | Set-Content -Path $out -Encoding UTF8
    Write-Host "Đã lưu (không chứa RTSP/ảnh): $out"
}
Write-Host "CAMERA_LAB/FACE_PILOT vẫn BLOCKED cho đến khi ký phê duyệt + Windows LAN thật."
