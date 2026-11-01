#Requires -Version 5.1
<#
.SYNOPSIS
  Kiểm tra camera EZVIZ theo từng bước (read-only diagnostics).
.DESCRIPTION
  KHÔNG nhận mật khẩu qua tham số. Script sẽ hỏi SecureString khi cần.
  TCP PASS không đồng nghĩa có video. ONVIF-listed ≠ RTSP đã kiểm chứng.
#>
param(
  [Parameter(Mandatory = $true)][string]$CameraHost,
  [int]$OnvifPort = 80,
  [int]$RtspPort = 554,
  [string]$OutDir = (Join-Path $env:TEMP "MyPCAttendance-CameraLab")
)

$ErrorActionPreference = "Continue"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$Report = [ordered]@{
  generated_at_local = (Get-Date).ToString("o")
  windows_version    = [System.Environment]::OSVersion.VersionString
  camera_host        = $CameraHost
  steps              = @()
}

function Add-Step($name, $status, $detail) {
  $script:Report.steps += [ordered]@{ name = $name; status = $status; detail_vi = $detail }
  Write-Host ("[{0}] {1}: {2}" -f $status, $name, $detail)
}

Add-Step "host_info" "PASS" ("PC={0}; IPv4 nội bộ sẽ liệt kê bên dưới" -f $env:COMPUTERNAME)
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" } |
  ForEach-Object { Add-Step "local_ip" "INFO" $_.IPAddress }

# TCP probes
foreach ($pair in @(@{n="tcp_onvif"; p=$OnvifPort}, @{n="tcp_rtsp"; p=$RtspPort})) {
  try {
    $tcp = Test-NetConnection -ComputerName $CameraHost -Port $pair.p -WarningAction SilentlyContinue
    if ($tcp.TcpTestSucceeded) {
      Add-Step $pair.n "PASS" ("TCP tới {0}:{1} thành công — chưa chứng minh phát được video" -f $CameraHost, $pair.p)
    } else {
      Add-Step $pair.n "FAIL" ("TCP tới {0}:{1} thất bại" -f $CameraHost, $pair.p)
    }
  } catch {
    Add-Step $pair.n "FAIL" $_.Exception.Message
  }
}

Add-Step "onvif_auth" "BLOCKED" "Cần chạy từ ứng dụng MyPC (nhập credential cục bộ). Không hỏi mật khẩu trên CLI Git."
Add-Step "rtsp_decode" "BLOCKED" "CAMERA_LAB_PASS chỉ đạt khi giải mã được khung hình thật trên máy Windows này."
Add-Step "live_preview" "BLOCKED" "Chưa có LIVE frame đã giải mã trong phiên kiểm tra script."

$path = Join-Path $OutDir ("camera-lab-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".json")
($Report | ConvertTo-Json -Depth 6) | Set-Content -Path $path -Encoding UTF8
Write-Host "Đã lưu báo cáo (đã redact): $path" -ForegroundColor Green
Write-Host "Trạng thái tổng: CAMERA_LAB = BLOCKED cho đến khi có khung hình LIVE thật." -ForegroundColor Yellow
