param([Parameter(Mandatory=$true)][string]$Commit, [string]$OutputDir = "$env:USERPROFILE\Downloads\MyPC-PR13-C11C14-Verify")
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$github = 'https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/' + $Commit + '/MyPC.Attendance/audit/handoffs/PR13-C11-C14-OUTBOX-CORRECT-20261103'
$files = @(@{ Name='MyPC.Attendance-CHANGED-PR13-C11C14-c2c7ba72e97a.zip' }, @{ Name='MyPC.Attendance-FULL-PR13-C11C14-c2c7ba72e97a.zip' })
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$manifestPath = Join-Path $OutputDir 'SHA256SUMS.txt'
Invoke-WebRequest -Uri ($github + '/SHA256SUMS.txt') -UseBasicParsing -OutFile $manifestPath
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8
Add-Type -AssemblyName System.IO.Compression.FileSystem
foreach ($spec in $files) {
  $name = [string]$spec.Name
  $destination = Join-Path $OutputDir $name
  Invoke-WebRequest -Uri ($github + '/' + $name) -UseBasicParsing -OutFile $destination
  $hashLine = @($manifest -split '\r?\n' | Where-Object { $_ -match ('\s+' + [regex]::Escape($name) + '$') })
  if ($hashLine.Count -ne 1) { throw "Missing SHA256 entry: $name" }
  $expectedSha = ([regex]::Match($hashLine[0], '^([0-9a-fA-F]{64})\s+')).Groups[1].Value.ToLowerInvariant()
  $actualSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash.ToLowerInvariant()
  if ($actualSha -ne $expectedSha) { throw "SHA256 FAIL: $name" }
  Write-Host ("PASS: {0} SHA256={1}" -f $name, $actualSha) -ForegroundColor Green
}
Write-Host ("feature_commit expected: c2c7ba72e97a176789d30bb4b94171e618c38720")
Write-Host ("Pass -Commit = GitHub PR HEAD tip after push")
