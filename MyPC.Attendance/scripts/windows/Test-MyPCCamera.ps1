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
Add-Step "rtsp_uri" "BLOCKED" "Cấu hình RTSP URI trong app (KHÔNG nhúng mật khẩu vào URI). Dùng /api/v1/cameras/gateway/live/configure — response chỉ có diagnostic_label REDACTED."
Add-Step "rtsp_decode" "BLOCKED" "TCP PASS ≠ RTSP decode. Gọi app API /gateway/health + /preview sau khi gắn LIVE; CAMERA_LAB_PASS chỉ khi giải mã khung hình thật và chủ sở hữu ký."
Add-Step "app_api_decode" "BLOCKED" "Khi backend chạy localhost: dùng phiên đăng nhập để đọc DECODED_MEASURED/FPS/frame_age — không tin TCP."
Add-Step "native_resolution" "BLOCKED" "Ghi DECODED_MEASURED width×height từ frame.shape (VENDOR_SPEC 2880×1620 không phải bằng chứng LIVE)."
Add-Step "face_pixel_quality" "BLOCKED" "Đo face width / inter-eye trên pixel gốc; không phóng to 2×/4× rồi tuyên bố đạt cổng ≥120px."
Add-Step "auto_enhance_shadow" "BLOCKED" "Chế độ hiệu lực mặc định AUTO_TEST_ONLY — ảnh gốc chính thức; enhanced chỉ A/B bóng đến khi pilot LIVE phê duyệt."
Add-Step "body_geometry" "BLOCKED" "Nếu góc cao không thấy đủ đầu–chân → BODY_CAPTURE_BLOCKED (đúng, không bịa)."
Add-Step "live_preview" "BLOCKED" "Preview phải cùng registry với gateway LIVE; provenance=CAMERA_LIVE; không thay MOCK ẩn."
Add-Step "evening_ir" "BLOCKED" "Kiểm tra DAY/DUSK/NIGHT_IR tại vị trí đánh dấu tầng 1 — cần owner chạy trên LAN công ty."
Add-Step "destination_pin" "INFO" "RTSP v1 chỉ chấp nhận IPv4 LAN literal; OpenCV mở URI đã ghim IP (không DNS TOCTOU)."
Add-Step "secret_entry" "INFO" "Nhập RTSP user/password trong UI localhost đã đăng nhập — không truyền -Password trên argv."
Add-Step "ffprobe_availability" "BLOCKED" "Kiểm tra ffprobe/OpenCV CAP_FFMPEG trên máy Windows này trước khi giải mã."
Add-Step "installer" "BLOCKED" "Installer Windows chưa được chứng minh trên máy này — giữ BLOCKED."
Add-Step "camera_lab_pass" "BLOCKED" "Giữ false cho đến khi đủ bằng chứng trên máy này."

# Optional: query local backend health without credentials in report
$BackendBase = $env:MYPC_BACKEND_BASE
if (-not $BackendBase) { $BackendBase = "http://127.0.0.1:8765" }
try {
  $health = Invoke-WebRequest -Uri ($BackendBase.TrimEnd('/') + "/api/v1/health") -UseBasicParsing -TimeoutSec 3
  if ($health.StatusCode -eq 200) {
    Add-Step "backend_health" "PASS" ("Backend local phản hồi {0} — chưa chứng minh RTSP decode." -f $health.StatusCode)
  } else {
    Add-Step "backend_health" "FAIL" ("HTTP {0}" -f $health.StatusCode)
  }
} catch {
  Add-Step "backend_health" "BLOCKED" "Backend local chưa chạy hoặc không tới được — không suy CAMERA_LAB PASS."
}

$Report | ConvertTo-Json -Depth 6 | Set-Content -Path $ReportPath -Encoding UTF8
Write-Host ""
Write-Host "Đã lưu báo cáo: $ReportPath" -ForegroundColor Cyan
Write-Host "camera_lab_pass=$($Report.camera_lab_pass) — không tự đánh PASS." -ForegroundColor Yellow
if ($OptionalRtspPath) {
  Write-Host "Gợi ý kiểm tra thủ công (không lưu mật khẩu): ffprobe <URI-đã-che>" -ForegroundColor DarkCyan
}
Write-Host "Owner: cấu hình RTSP IPv4 trong app → /gateway/health + /preview → ký CAMERA_LAB khi đủ bằng chứng." -ForegroundColor DarkCyan
