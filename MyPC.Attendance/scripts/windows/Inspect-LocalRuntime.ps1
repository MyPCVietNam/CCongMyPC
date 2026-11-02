#Requires -Version 5.1
<#
Read-only MyPC Attendance local readiness check.
Does NOT open, read, echo or export passwords, cookies, camera URLs or SQLite content.
No required admin rights. ASCII-only source for Windows PowerShell 5.1.
#>
[CmdletBinding()]
param(
    [string]$ApplicationRoot = "$env:USERPROFILE\Downloads\CCongMyPC-PR10\MyPC.Attendance",
    [string]$CameraHost = "192.168.0.211"
)
$ErrorActionPreference = 'Stop'
$checks = New-Object System.Collections.ArrayList
function Check([string]$Name,[string]$Status,[string]$Note) {
    [void]$checks.Add([pscustomobject]@{ Name=$Name; Status=$Status; Note=$Note })
}
if (Test-Path -LiteralPath $ApplicationRoot -PathType Container) {
    Check 'SourceRoot' 'PRESENT' 'Application directory exists'
} else {
    Check 'SourceRoot' 'NOT_FOUND' 'Supply -ApplicationRoot pointing to MyPC.Attendance'
}
try {
    if (Test-Path -LiteralPath (Join-Path $ApplicationRoot '..\.git')) {
        $head = (& git -C $ApplicationRoot rev-parse HEAD 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -eq 0) { Check 'GitHead' 'MEASURED' $head }
        else { Check 'GitHead' 'NOT_RUN' 'Git command failed' }
    } else {
        $head = (& git -C $ApplicationRoot rev-parse HEAD 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -eq 0) { Check 'GitHead' 'MEASURED' $head }
        else { Check 'GitHead' 'NOT_RUN' 'Not a verified git working tree' }
    }
} catch { Check 'GitHead' 'NOT_RUN' 'Cannot identify repository' }
$profiles = @(
    @{Name='LOCALAPPDATA'; Path=(Join-Path $env:LOCALAPPDATA 'MyPC\Attendance\data')},
    @{Name='PROGRAMDATA'; Path=(Join-Path $env:ProgramData 'MyPC\Attendance\data')},
    @{Name='REPO_LOCAL'; Path=(Join-Path $ApplicationRoot 'data')}
)
foreach ($profile in $profiles) {
    $exists = Test-Path -LiteralPath $profile.Path -PathType Container
    $db = Test-Path -LiteralPath (Join-Path $profile.Path 'mypc_attendance.sqlite3') -PathType Leaf
    $first = Test-Path -LiteralPath (Join-Path $profile.Path 'FIRST_RUN_ADMIN.txt') -PathType Leaf
    Check ("DataProfile_" + $profile.Name) 'MEASURED' ("dir=" + $exists + "; db=" + $db + "; bootstrapFile=" + $first)
}
if ($env:MYPC_DATA_DIR) { Check 'MYPC_DATA_DIR' 'SET' 'Explicit env profile selected (value redacted)' }
else { Check 'MYPC_DATA_DIR' 'UNSET' 'Check process environment; another process may use a different path' }
$python = Join-Path $ApplicationRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $python -PathType Leaf) {
    try {
        $result = & $python -c "import sys, cv2; print('Python '+sys.version.split()[0]+'; OpenCV '+cv2.__version__+'; FaceDetectorYN '+str(hasattr(cv2,'FaceDetectorYN'))+'; FaceRecognizerSF '+str(hasattr(cv2,'FaceRecognizerSF')))" 2>$null
        if ($LASTEXITCODE -eq 0) { Check 'PythonOpenCV' 'PASS' (($result | Out-String).Trim()) }
        else { Check 'PythonOpenCV' 'FAIL' 'Cannot import cv2 within app venv' }
    } catch { Check 'PythonOpenCV' 'FAIL' 'OpenCV import failure; no diagnostics echoed' }
} else { Check 'PythonOpenCV' 'NOT_FOUND' 'No application Python virtual environment' }
foreach ($command in @('ffprobe.exe','node.exe','npm.cmd')) {
    if (Get-Command $command -ErrorAction SilentlyContinue) { Check $command 'PRESENT' 'Command found' }
    else { Check $command 'NOT_FOUND' 'Command missing from PATH' }
}
$index = Join-Path $ApplicationRoot 'backend\app\static\index.html'
if (Test-Path -LiteralPath $index -PathType Leaf) { Check 'FrontendBuild' 'PRESENT' 'Build index exists' }
else { Check 'FrontendBuild' 'NOT_FOUND' 'Use npm.cmd ci and npm.cmd run build' }
try {
    $resp = Invoke-WebRequest -Uri 'http://127.0.0.1:8765/' -TimeoutSec 4 -UseBasicParsing
    Check 'LocalHTTP' 'MEASURED' ("HTTP " + $resp.StatusCode + " (not camera LIVE evidence)")
} catch { Check 'LocalHTTP' 'UNAVAILABLE' 'Backend not responding at 127.0.0.1:8765' }
try {
    $port = Test-NetConnection -ComputerName $CameraHost -Port 554 -InformationLevel Quiet -WarningAction SilentlyContinue
    Check 'CameraTCP' ($(if($port){'REACHABLE'}else{'UNREACHABLE'})) 'TCP only; RTSP decode NOT MEASURED'
} catch { Check 'CameraTCP' 'NOT_RUN' 'Network check unavailable' }
Check 'CAMERA_LAB' 'BLOCKED' 'Must have true decoded LIVE evidence and owner approval'
Check 'FACE_PILOT' 'BLOCKED' 'Must have consented labeled real-model evidence'
Check 'INSTALLER' 'BLOCKED' 'Must have real Windows installer validation'
$checks | Format-Table Name,Status,Note -Wrap -AutoSize
Write-Host 'NO credentials, biometric media or database content were accessed.'
