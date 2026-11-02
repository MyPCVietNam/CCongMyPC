#Requires -Version 5.1
<#
Optional owner-only check of an existing FIRST_RUN_ADMIN.txt against localhost.
Requires explicit -Check switch; makes ONE local login request.
Outputs ONLY a sanitized status. Does not change password, state or database.
Never provide this file or its contents to support/chat.
This helper transiently reads the plaintext secret into process memory.
#>
[CmdletBinding()]
param(
    [switch]$Check,
    [string]$DataDirectory = ''
)
$ErrorActionPreference='Stop'
if (-not $Check) { throw 'Explicit -Check is required. No request was sent.' }
$paths = @(
    (Join-Path $env:LOCALAPPDATA 'MyPC\Attendance\data'),
    (Join-Path $env:ProgramData 'MyPC\Attendance\data')
)
if ($DataDirectory) { $paths = @($DataDirectory) }
else {
    $paths = @($paths | Where-Object { Test-Path -LiteralPath (Join-Path $_ 'FIRST_RUN_ADMIN.txt') -PathType Leaf })
    if ($paths.Count -gt 1) { Write-Output 'MULTIPLE_PROFILES: choose -DataDirectory explicitly, no credentials read'; exit 2 }
}
if ($paths.Count -eq 0) { Write-Output 'FILE_NOT_FOUND: no first-run file in known profiles'; exit 1 }
$file = Join-Path $paths[0] 'FIRST_RUN_ADMIN.txt'
if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { Write-Output 'FILE_NOT_FOUND'; exit 1 }
try {
    $listeners = @(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction Stop)
    $unsafe = @($listeners | Where-Object { $_.LocalAddress -notin @('127.0.0.1','::1') })
    if ($listeners.Count -eq 0 -or $unsafe.Count -gt 0) {
        Write-Output 'LOCAL_SERVER_NOT_TRUSTED: verify listener binds to loopback only'; exit 3
    }
} catch { Write-Output 'LOCAL_SERVER_UNVERIFIED'; exit 3 }
$username = $null
$password = $null
$content = $null
$body = $null
try {
    $content = [System.IO.File]::ReadAllLines($file, [Text.Encoding]::UTF8)
    foreach ($line in $content) {
        if ($line.StartsWith('username=')) { $username = $line.Substring(9) }
        if ($line.StartsWith('password=')) { $password = $line.Substring(9) }
    }
    if (-not $username -or -not $password) { Write-Output 'INVALID_LOCAL_SECRET_FILE'; exit 4 }
    # Fixed literal localhost; NEVER accept a remote base URL here.
    $body = @{username=$username;password=$password} | ConvertTo-Json -Compress
    $null = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8765/api/v1/auth/login' -ContentType 'application/json' -Body $body -TimeoutSec 5
    Write-Output 'AUTH_ACCEPTED: local stored first-run credential is recognized; no password displayed'
} catch {
    Write-Output 'AUTH_REJECTED_OR_UNAVAILABLE: check profile and use audited owner recovery; do not brute force'
    exit 5
} finally {
    $username=$null; $password=$null; $content=$null; $body=$null
}
