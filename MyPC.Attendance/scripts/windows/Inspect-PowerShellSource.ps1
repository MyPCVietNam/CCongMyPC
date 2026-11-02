#Requires -Version 5.1
<# Read-only parser and source-encoding audit of repository .ps1 files. #>
[CmdletBinding()]
param([string]$ApplicationRoot="$env:USERPROFILE\Downloads\CCongMyPC-PR10\MyPC.Attendance")
$ErrorActionPreference='Stop'
if (-not (Test-Path -LiteralPath $ApplicationRoot -PathType Container)) { throw 'ApplicationRoot does not exist' }
$failed=0
$files=@(Get-ChildItem -LiteralPath (Join-Path $ApplicationRoot 'scripts\windows') -Filter '*.ps1' -File -Recurse -ErrorAction Stop)
foreach($file in $files) {
    $bytes=[IO.File]::ReadAllBytes($file.FullName)
    $hasBom=($bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191)
    $hasNonAscii=(@($bytes | Where-Object { $_ -ge 128 }).Count -gt 0)
    $tok=$null; $errors=$null
    $null=[System.Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tok,[ref]$errors)
    $status=if($errors.Count -gt 0){'PARSER_FAIL'}elseif($hasNonAscii -and -not $hasBom){'UTF8_COMPAT_RISK'}else{'PASS'}
    if($status -ne 'PASS'){$failed++}
    Write-Output ([pscustomobject]@{Name=$file.Name;Status=$status;UTF8BOM=$hasBom;ParseErrorCount=$errors.Count})
}
if($failed -gt 0){Write-Output "SCANNED=$($files.Count); PROBLEMS=$failed"; exit 1}
Write-Output "SCANNED=$($files.Count); PROBLEMS=0"
