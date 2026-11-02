# MyPC Attendance — read-only diagnostics for Windows PowerShell 5.1
# UTF-8 BOM required. Never assign $HOME / $home.
param(
    [string]$DataDir = ""
)

$ErrorActionPreference = 'Stop'
$attendanceHome = Join-Path $env:LOCALAPPDATA 'MyPC\Attendance'
if (-not $DataDir) {
    $DataDir = Join-Path $attendanceHome 'data'
}

Write-Host "MYPC_DIAGNOSTICS_READONLY"
Write-Host ("ATTENDANCE_HOME=" + $attendanceHome)
Write-Host ("DATA_DIR=" + $DataDir)
Write-Host ("IDENTITY=" + [Security.Principal.WindowsIdentity]::GetCurrent().Name)

$secrets = Join-Path $DataDir 'secrets'
if (Test-Path -LiteralPath $secrets) {
    Write-Host 'SECRETS_DIR=PRESENT'
    foreach ($name in @('session.secret','master.key','face_templates.key')) {
        $p = Join-Path $secrets $name
        if (Test-Path -LiteralPath $p -PathType Leaf) {
            Write-Host ("SECRET_PRESENT " + $name + " bytes=" + (Get-Item -LiteralPath $p).Length)
        } else {
            Write-Host ("SECRET_MISSING " + $name)
        }
    }
} else {
    Write-Host 'SECRETS_DIR=MISSING'
}

$listener = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if ($listener) { Write-Host 'PORT_8765=LISTEN' } else { Write-Host 'PORT_8765=FREE' }

Write-Host 'NOTE: No passwords, frames, embeddings, or employee PII are printed.'
Write-Host 'CAMERA_LAB/FACE_PILOT/EXIT/INSTALLER remain BLOCKED without owner physical evidence.'
