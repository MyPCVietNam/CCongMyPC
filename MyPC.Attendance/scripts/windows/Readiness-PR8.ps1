#Requires -Version 5.1
<#
.SYNOPSIS
  Kiểm tra sẵn sàng máy Windows (chỉ đọc) cho MyPC Attendance / camera EZVIZ.
.DESCRIPTION
  Không nhận mật khẩu RTSP. Không mở cổng WAN. Không đánh CAMERA_LAB/FACE_PILOT PASS.
  Tương thích Windows PowerShell 5.1 và PowerShell 7.
#>
[CmdletBinding()]
param(
    [string]$CameraHost = "",
    [int]$RtspPort = 554,
    [string]$OutputDirectory = ""
)
$ErrorActionPreference = 'Stop'
$pin = '8c5b20058e6777bb61666e541e8fa5ba65a770e9'
$checks = New-Object System.Collections.ArrayList
function Add-Check([string]$Name, [string]$Status, [string]$Detail) {
    [void]$checks.Add([pscustomobject]@{ Name = $Name; Status = $Status; Detail = $Detail })
}
function Test-Executable([string]$Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $cmd) { Add-Check $Name 'NOT_FOUND' 'Cài từ nhà cung cấp chính thức'; return }
    $line = $Name
    try { $line = ((& $Name --version 2>&1 | Select-Object -First 1) | Out-String).Trim() } catch { $line = 'Đã thấy; không lấy được phiên bản' }
    Add-Check $Name 'PRESENT' $line
}
Add-Check 'Host' 'MEASURED' ([System.Environment]::OSVersion.VersionString)
Add-Check 'PSVersion' 'MEASURED' ($PSVersionTable.PSVersion.ToString())
Add-Check 'Is64Bit' 'MEASURED' ([System.Environment]::Is64BitOperatingSystem.ToString())
try {
    $os = Get-CimInstance Win32_OperatingSystem
    $freeGb = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
    Add-Check 'RAM_Free_GB' 'MEASURED' "$freeGb"
} catch { Add-Check 'RAM_Free_GB' 'NOT_RUN' 'Không đọc được CIM' }
foreach ($name in @('python', 'py', 'node', 'npm', 'git', 'ffprobe')) { Test-Executable $name }
try {
    $repoRoot = (git rev-parse --show-toplevel 2>$null)
    if ($repoRoot) { $repoRoot = $repoRoot.Trim() }
    $head = (git rev-parse HEAD 2>$null)
    if ($head) { $head = $head.Trim() }
    if ($head -eq $pin) { Add-Check 'SourcePin' 'PASS_EXACT' $head }
    elseif ($repoRoot -and $head) {
        git merge-base --is-ancestor $pin HEAD 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { Add-Check 'SourcePin' 'PASS_DESCENDANT' $head }
        else { Add-Check 'SourcePin' 'FAIL' 'HEAD không chứa commit PR8 đã ghim' }
    } else { Add-Check 'SourcePin' 'NOT_RUN' 'Không có Git working tree' }
} catch { Add-Check 'SourcePin' 'NOT_RUN' 'Git không khả dụng' }
$portUsed = $false
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $async = $tcp.BeginConnect('127.0.0.1', 8765, $null, $null)
    if ($async.AsyncWaitHandle.WaitOne(500, $false)) {
        try { $tcp.EndConnect($async); $portUsed = $true } catch {}
    }
    $tcp.Close()
} catch {}
Add-Check 'LocalPort8765' ($(if ($portUsed) { 'IN_USE' } else { 'FREE' })) 'Chỉ localhost; không chứng minh app đang chạy đúng'
if ($CameraHost) {
    if ($CameraHost -notmatch '^\d{1,3}(\.\d{1,3}){3}$') {
        Add-Check 'CameraTCP' 'BLOCKED' 'Chỉ chấp nhận IPv4 literal nội bộ trong helper này'
    } else {
        $valid = $true
        foreach ($o in $CameraHost.Split('.')) { if ([int]$o -gt 255) { $valid = $false } }
        if (-not $valid) { Add-Check 'CameraTCP' 'BLOCKED' 'IPv4 không hợp lệ' }
        else {
            try {
                $probe = Test-NetConnection -ComputerName $CameraHost -Port $RtspPort -WarningAction SilentlyContinue -InformationLevel Quiet
                Add-Check 'CameraTCP' ($(if ($probe) { 'TCP_REACHABLE' } else { 'TCP_UNREACHABLE' })) 'TCP ≠ RTSP decode ≠ CAMERA_LAB PASS'
            } catch { Add-Check 'CameraTCP' 'NOT_RUN' 'Không hoàn tất probe mạng' }
        }
    }
} else {
    Add-Check 'CameraTCP' 'NOT_RUN' 'Chưa cung cấp host — cấu hình camera chỉ trong UI đã xác thực'
}
Add-Check 'CAMERA_LAB' 'BLOCKED' 'Cần lab-run LIVE đo trên Windows LAN + owner review'
Add-Check 'FACE_PILOT' 'BLOCKED' 'Cần case KNOWN/UNKNOWN do server đo (đồng ý mẫu)'
Add-Check 'EXIT_VERIFICATION' 'BLOCKED' 'Cần bằng chứng ra về vật lý'
Add-Check 'INSTALLER' 'BLOCKED' 'Cần kiểm tra bộ cài thật trên Windows'
$report = [pscustomobject]@{
    schema     = 'mypc.pr8.preflight.v1'
    run_utc    = [DateTime]::UtcNow.ToString('o')
    target_pin = $pin
    checks     = @($checks)
}
$report | Format-List | Out-String | Write-Output
if ($OutputDirectory) {
    if (-not (Test-Path $OutputDirectory)) {
        New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    }
    $report | ConvertTo-Json -Depth 8 |
        Set-Content -Path (Join-Path $OutputDirectory 'pr8-windows-preflight-sanitized.json') -Encoding UTF8
}
Write-Output 'Không thu ảnh khuôn mặt / mật khẩu RTSP. Cổng vật lý vẫn BLOCKED.'
