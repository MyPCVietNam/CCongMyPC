#Requires -Version 5.1
<#
.SYNOPSIS
  Kiểm tra camera EZVIZ theo từng bước (đọc-only diagnostics) trên Windows.
.DESCRIPTION
  KHÔNG nhận mật khẩu qua tham số. Script hỏi SecureString khi cần ONVIF.
  TCP PASS ≠ có video. ONVIF-listed ≠ RTSP đã giải mã. CAMERA_LAB_PASS chỉ
  khi máy Windows này giải mã được khung hình thật và ghi bằng chứng.
.NOTES
  Không đổi ExecutionPolicy máy. Chạy: powershell -ExecutionPolicy Bypass -File .\Test-MyPCCamera.ps1 -CameraHost <IP>
#>
param(
  [Parameter(Mandatory = $true)][string]$CameraHost,
  [int]$OnvifPort = 80,
  [int]$RtspPort = 554,
  [string]$OutDir = (Join-Path $env:ProgramData "MyPC\Attendance\camera-lab"),
  [string]$OptionalRtspPath = ""
)

$ErrorActionPreference = "Continue"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ReportPath = Join-Path $OutDir ("camera-lab-" + $stamp + ".json")
$Report = [ordered]@{
  generated_at_local = (Get-Date).ToString("o")
  timezone_note      = "Giờ local Windows; đối chiếu Asia/Ho_Chi_Minh trong ứng dụng"
  windows_version    = [System.Environment]::OSVersion.VersionString
  camera_host        = $CameraHost
  camera_lab_pass    = $false
  steps              = @()
}

function Add-Step($name, $status, $detail) {
  $script:Report.steps += [ordered]@{ name = $name; status = $status; detail_vi = $detail }
  Write-Host ("[{0}] {1}: {2}" -f $status, $name, $detail)
}

Add-Step "host_info" "PASS" ("PC={0}" -f $env:COMPUTERNAME)
Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -notlike "127.*" } |
  ForEach-Object { Add-Step "local_ip" "INFO" $_.IPAddress }

foreach ($pair in @(@{n="tcp_onvif"; p=$OnvifPort}, @{n="tcp_rtsp"; p=$RtspPort})) {
  try {
    $tcp = Test-NetConnection -ComputerName $CameraHost -Port $pair.p -WarningAction SilentlyContinue
    if ($tcp.TcpTestSucceeded) {
      Add-Step $pair.n "PASS" ("TCP {0}:{1} OK — chưa chứng minh video" -f $CameraHost, $pair.p)
    } else {
      Add-Step $pair.n "FAIL" ("TCP {0}:{1} thất bại" -f $CameraHost, $pair.p)
    }
  } catch {
    Add-Step $pair.n "FAIL" $_.Exception.Message
  }
}

Add-Step "onvif_auth" "BLOCKED" "Nhập credential trong Cài đặt camera của ứng dụng (không ghi mật khẩu vào JSON này)."
Add-Step "rtsp_uri" "BLOCKED" "Cấu hình RTSP URI trong app; gateway LIVE dùng /api/v1/cameras/gateway/live/configure — URI trả về đã che mật khẩu."
Add-Step "rtsp_decode" "BLOCKED" "CAMERA_LAB_PASS chỉ đạt khi giải mã được khung hình thật trên máy Windows này (ffmpeg/OpenCV)."
Add-Step "native_resolution" "BLOCKED" "Ghi width×height khung native sau khi decode thành công."
Add-Step "face_pixel_quality" "BLOCKED" "Đo face width / inter-eye tại vị trí đứng đăng ký; không phóng to kỹ thuật số rồi tuyên bố đạt."
Add-Step "body_geometry" "BLOCKED" "Nếu góc cao không thấy đủ đầu–chân → BODY_CAPTURE_BLOCKED (đúng, không bịa)."
Add-Step "live_preview" "BLOCKED" "Xem /api/v1/cameras/gateway/health — provenance phải là CAMERA_LIVE, không phải MOCK."
Add-Step "camera_lab_pass" "BLOCKED" "Giữ false cho đến khi đủ bằng chứng trên máy này."

$Report | ConvertTo-Json -Depth 6 | Set-Content -Path $ReportPath -Encoding UTF8
Write-Host ""
Write-Host "Đã lưu báo cáo: $ReportPath" -ForegroundColor Cyan
Write-Host "camera_lab_pass=$($Report.camera_lab_pass) — không tự đánh PASS." -ForegroundColor Yellow
if ($OptionalRtspPath) {
  Write-Host "Gợi ý kiểm tra thủ công (không lưu mật khẩu): ffprobe <URI-đã-che>" -ForegroundColor DarkCyan
}
