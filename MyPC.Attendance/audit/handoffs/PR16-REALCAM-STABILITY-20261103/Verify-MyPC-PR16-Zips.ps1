# Verify PR16 ZIPs against SHA256SUMS.txt.
# Required ZIP hashes = ERROR on mismatch.
# Extra docs not listed = WARNING (scope), not hard failure.
param(
  [Parameter(Mandatory = $true)][string]$Commit,
  [string]$OutDir = $PSScriptRoot
)
$ErrorActionPreference = 'Stop'
$github = 'https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/' + $Commit + '/MyPC.Attendance/audit/handoffs/PR16-REALCAM-STABILITY-20261103'
$sumsUrl = "$github/SHA256SUMS.txt"
Write-Host "Fetching $sumsUrl"
Invoke-WebRequest -Uri $sumsUrl -UseBasicParsing -OutFile (Join-Path $OutDir 'SHA256SUMS.downloaded.txt')
$required = @{}
Get-Content (Join-Path $OutDir 'SHA256SUMS.downloaded.txt') | ForEach-Object {
  if ($_ -match '^\s*([0-9a-fA-F]{64})\s+(\S+)\s*$') {
    $required[$Matches[2]] = $Matches[1].ToLowerInvariant()
  }
}
$fail = 0
foreach ($name in $required.Keys) {
  $local = Join-Path $OutDir $name
  if (-not (Test-Path $local)) {
    $zipUrl = "$github/$name"
    Write-Host "Downloading $zipUrl"
    try {
      Invoke-WebRequest -Uri $zipUrl -OutFile $local -UseBasicParsing
    } catch {
      Write-Host "ERROR: missing required $name"
      $fail++
      continue
    }
  }
  $sha = (Get-FileHash -Algorithm SHA256 -Path $local).Hash.ToLowerInvariant()
  if ($sha -ne $required[$name]) {
    Write-Host "ERROR: HASH MISMATCH $name"
    $fail++
  } else {
    Write-Host "PASS $name"
  }
}
Get-ChildItem -Path $OutDir -File | ForEach-Object {
  if ($_.Name -match '\.(zip)$' -and -not $required.ContainsKey($_.Name)) {
    Write-Host "WARNING: Not listed in SHA256SUMS.txt (docs/extra scope): $($_.Name)"
  }
}
if ($fail -gt 0) { throw "SHA256 verification failed ($fail)" }
Write-Host 'Required ZIP hashes matched. Extra files are warnings only.'
