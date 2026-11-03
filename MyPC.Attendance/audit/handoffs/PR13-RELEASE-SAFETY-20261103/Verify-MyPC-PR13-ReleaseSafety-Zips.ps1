# Read-only GitHub ZIP verifier — pass -Commit = actual GitHub PR HEAD after push.
param(
  [Parameter(Mandatory = $true)][string]$Commit,
  [string]$OutDir = $PSScriptRoot
)
$ErrorActionPreference = 'Stop'
$github = 'https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/' + $Commit + '/MyPC.Attendance/audit/handoffs/PR13-RELEASE-SAFETY-20261103'
$sumsUrl = "$github/SHA256SUMS.txt"
Write-Host "Fetching $sumsUrl"
$sums = Invoke-WebRequest -Uri $sumsUrl -UseBasicParsing
$sums.Content | Set-Content -Path (Join-Path $OutDir 'SHA256SUMS.downloaded.txt') -Encoding utf8
Get-Content (Join-Path $OutDir 'SHA256SUMS.downloaded.txt') | ForEach-Object {
  if ($_ -match '^\s*([0-9a-fA-F]{64})\s+(\S+)\s*$') {
    $expect = $Matches[1].ToLowerInvariant()
    $name = $Matches[2]
    $local = Join-Path $OutDir $name
    if (-not (Test-Path $local)) {
      $zipUrl = "$github/$name"
      Write-Host "Downloading $zipUrl"
      Invoke-WebRequest -Uri $zipUrl -OutFile $local -UseBasicParsing
    }
    $sha = (Get-FileHash -Algorithm SHA256 -Path $local).Hash.ToLowerInvariant()
    if ($sha -ne $expect) { throw "HASH MISMATCH $name expect=$expect got=$sha" }
    Write-Host "PASS $name"
  }
}
Write-Host 'All listed ZIP hashes matched.'
