#Requires -Version 5.1
<#
.SYNOPSIS
  Gọi API localhost đã đăng nhập để lấy DECODED_MEASURED / FPS (không nhận mật khẩu RTSP).
.DESCRIPTION
  Đọc session cookie + CSRF từ tham số an toàn (SecureString token đã có sẵn).
  Không đánh CAMERA_LAB PASS. Không ghi URI/credential vào JSON.
#>
param(
  [string]$BaseUrl = "http://127.0.0.1:8765",
  [Parameter(Mandatory = $true)][int]$CameraId,
  [Parameter(Mandatory = $true)][string]$CsrfToken,
  [Parameter(Mandatory = $true)][string]$SessionCookie,
  [string]$OutDir = (Join-Path $env:ProgramData "MyPC\Attendance\camera-lab")
)

$ErrorActionPreference = "Continue"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$out = Join-Path $OutDir ("api-diag-" + $stamp + ".json")
$hdr = @{
  "X-CSRF-Token" = $CsrfToken
  "Cookie"       = ("mypc_session=" + $SessionCookie)
}
$report = [ordered]@{
  generated_at_local = (Get-Date).ToString("o")
  camera_id          = $CameraId
  camera_lab_pass    = $false
  steps              = @()
}
function Add-Step($n, $s, $d) {
  $script:report.steps += [ordered]@{ name = $n; status = $s; detail_vi = $d }
}

try {
  $h = Invoke-RestMethod -Uri ($BaseUrl.TrimEnd('/') + "/api/v1/cameras/gateway/health?camera_id=$CameraId") -Headers $hdr
  Add-Step "gateway_health" "INFO" ("ready={0}; settings_flag={1}; signed_lab={2}; camera_lab_pass={3}" -f $h.ready, $h.settings_flag_camera_lab, $h.signed_camera_lab, $h.camera_lab_pass)
  if ($h.sources) {
    foreach ($s in $h.sources) {
      Add-Step "source" "INFO" ("prov={0}; decoded={1}x{2}; fps={3}; op_ready={4}" -f $s.provenance, $s.native_width, $s.native_height, $s.fps_estimate, $s.operationally_ready)
    }
  }
} catch {
  Add-Step "gateway_health" "BLOCKED" $_.Exception.Message
}

try {
  $null = Invoke-WebRequest -Uri ($BaseUrl.TrimEnd('/') + "/api/v1/cameras/$CameraId/preview") -Headers $hdr -UseBasicParsing
  Add-Step "preview" "INFO" "Preview HTTP OK — kiểm tra provenance CAMERA_LIVE trên UI; không suy PASS."
} catch {
  Add-Step "preview" "BLOCKED" $_.Exception.Message
}

Add-Step "camera_lab_pass" "BLOCKED" "Giữ false đến khi có evidence PHYSICAL_VERIFIED + phê duyệt đã ký trên Windows LAN."
$report | ConvertTo-Json -Depth 6 | Set-Content -Path $out -Encoding UTF8
Write-Host "Đã lưu: $out — camera_lab_pass=false"
