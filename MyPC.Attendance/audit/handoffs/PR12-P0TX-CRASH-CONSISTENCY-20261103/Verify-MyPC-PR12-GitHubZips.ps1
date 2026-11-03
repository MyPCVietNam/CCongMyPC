# Read-only GitHub ZIP verifier — set $Commit to actual GitHub PR HEAD after push (not feature_commit).
# PowerShell 5.1 compatible; downloads archives only; never runs extracted code.
param(
    [Parameter(Mandatory=$true)][string]$Commit,
    [string]$OutputDir = "$env:USERPROFILE\Downloads\MyPC-PR12-P0TX-CRASH-Verify"
)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$github = 'https://raw.githubusercontent.com/MyPCVietNam/CCongMyPC/' + $Commit + '/MyPC.Attendance/audit/handoffs/PR12-P0TX-CRASH-CONSISTENCY-20261103'
$files = @(
    @{ Name='MyPC.Attendance-CHANGED-PR12-P0TX-CRASH-4eba3d67a534.zip' },
    @{ Name='MyPC.Attendance-FULL-PR12-P0TX-CRASH-4eba3d67a534.zip' }
)
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
    if ($hashLine.Count -ne 1) { throw "Missing/ambiguous SHA256 manifest entry: $name" }
    $matchSha = [regex]::Match($hashLine[0], '^([0-9a-fA-F]{64})\s+')
    if (-not $matchSha.Success) { throw "Malformed SHA256 manifest entry: $name" }
    $expectedSha = $matchSha.Groups[1].Value.ToLowerInvariant()
    $actualSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash.ToLowerInvariant()
    if ($actualSha -ne $expectedSha) { throw "SHA256 FAIL: $name expected=$expectedSha actual=$actualSha" }
    $archive = [System.IO.Compression.ZipFile]::OpenRead($destination)
    try {
        Write-Host ("PASS: {0} SHA256={1} ENTRIES={2}" -f $name, $actualSha, $archive.Entries.Count) -ForegroundColor Green
    } finally { $archive.Dispose() }
}
$feat = Invoke-WebRequest -Uri ($github + '/FEATURE_COMMIT.txt') -UseBasicParsing
Write-Host ("feature_commit file: " + $feat.Content.Trim())
Write-Host ("Verify GitHub PR HEAD separately: gh pr view 12 --json headRefOid (must equal -Commit $Commit)")
