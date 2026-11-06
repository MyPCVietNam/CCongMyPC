#Requires -Version 5.1
<#
.SYNOPSIS
  Safe isolated USB candidate on 127.0.0.1:18878 only (P02-USB-HF1).
  Modes: Prepare | Preflight | Start | Export
  NEVER touches 18876/18877 DataDirs, SQLite, secrets, RTSP credentials, photos, embeddings.

.EXAMPLE
  .\p02_usb_hf1_candidate_18878.ps1 -Mode Prepare -FullSourceZip C:\path\MyPC.Attendance-FULL-SOURCE-P02-USB-HF1.zip -ExpectedSha256 <hex>
  .\p02_usb_hf1_candidate_18878.ps1 -Mode Preflight
  .\p02_usb_hf1_candidate_18878.ps1 -Mode Start
  .\p02_usb_hf1_candidate_18878.ps1 -Mode Export
#>
param(
  [ValidateSet("Prepare", "Preflight", "Start", "Export")]
  [string]$Mode = "Preflight",
  [string]$CandidateRoot = "$env:LOCALAPPDATA\MyPC.Attendance\p02-usb-hf1-candidate",
  [string]$FullSourceZip = "",
  [string]$ExpectedSha256 = "",
  [string]$ModelsSourceDir = "",
  [int]$Port = 18878
)

$ErrorActionPreference = "Stop"
$Utf8Bom = New-Object System.Text.UTF8Encoding $true

function Write-Log([string]$Msg) {
  $line = "[{0}] {1}" -f (Get-Date).ToUniversalTime().ToString("o"), $Msg
  Write-Host $line
  $logDir = Join-Path $CandidateRoot "logs"
  New-Item -ItemType Directory -Force -Path $logDir | Out-Null
  [System.IO.File]::AppendAllText((Join-Path $logDir "candidate.log"), $line + "`r`n", $Utf8Bom)
}

function Assert-PortSafe {
  if ($Port -ne 18878) { throw "Port must be 18878 (got $Port). Refusing." }
  foreach ($bad in @(18876, 18877)) {
    if ($Port -eq $bad) { throw "Refusing owner staging port $bad" }
  }
}

function Get-Sha256Lower([string]$Path) {
  return (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

Assert-PortSafe
New-Item -ItemType Directory -Force -Path $CandidateRoot | Out-Null
$dataDir = Join-Path $CandidateRoot "DataDir"
$srcDir = Join-Path $CandidateRoot "src"
$exportDir = Join-Path $CandidateRoot "export"

switch ($Mode) {
  "Prepare" {
    if (-not $FullSourceZip -or -not (Test-Path $FullSourceZip)) {
      throw "Prepare requires -FullSourceZip pointing to FULL-SOURCE ZIP"
    }
    if (-not $ExpectedSha256) { throw "Prepare requires -ExpectedSha256 (lowercase hex)" }
    $got = Get-Sha256Lower $FullSourceZip
    if ($got -ne $ExpectedSha256.ToLowerInvariant()) {
      throw "SHA256 mismatch: got $got expected $($ExpectedSha256.ToLowerInvariant())"
    }
    Write-Log "SHA256 PIN_MATCH for FULL-SOURCE ZIP"
    if (Test-Path $srcDir) { Remove-Item -Recurse -Force $srcDir }
    New-Item -ItemType Directory -Force -Path $srcDir | Out-Null
    Expand-Archive -Path $FullSourceZip -DestinationPath $srcDir -Force
    New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
    # Optional: copy ONLY already-PIN_MATCH model weights (never DataDir/SQLite/secrets)
    if ($ModelsSourceDir -and (Test-Path $ModelsSourceDir)) {
      $modelsDst = Join-Path $CandidateRoot "models"
      New-Item -ItemType Directory -Force -Path $modelsDst | Out-Null
      Get-ChildItem $ModelsSourceDir -Filter "*.onnx" | ForEach-Object {
        Copy-Item $_.FullName -Destination (Join-Path $modelsDst $_.Name) -Force
        Write-Log ("Copied model weight name-only: {0} sha={1}" -f $_.Name, (Get-Sha256Lower $_.FullName))
      }
    }
    Write-Log "Prepare OK — empty DataDir at $dataDir (do not copy owner SQLite/secrets)"
  }
  "Preflight" {
    Write-Log "Preflight port=$Port candidate=$CandidateRoot"
    if ($Port -in @(18876, 18877)) { throw "Refuse owner ports" }
    $busy = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($busy) { Write-Log "WARN: port $Port already in use — stop that process before Start" }
    else { Write-Log "Port $Port appears free" }
    Write-Log "Reminders: UGREEN PnP hashed + DirectShow link; measure actual 1080p; do not paste HMAC into chat"
  }
  "Start" {
    $backend = Join-Path $srcDir "MyPC.Attendance\backend"
    if (-not (Test-Path $backend)) {
      # FULL zip may nest differently
      $alt = Get-ChildItem $srcDir -Recurse -Directory -Filter backend | Select-Object -First 1
      if ($alt) { $backend = $alt.FullName }
    }
    if (-not (Test-Path $backend)) { throw "backend not found under $srcDir — run Prepare first" }
    $env:MYPC_DATA_DIR = $dataDir
    $env:DATA_DIR = $dataDir
    Write-Log "Start candidate backend DataDir=$dataDir Port=$Port (operator must launch uvicorn/app with these env vars)"
    Write-Log "Open http://127.0.0.1:$Port — footer MyPC Việt Nam https://mypc.vn"
    Write-Host "Set DATA_DIR=$dataDir then start the app bound to 127.0.0.1:$Port from: $backend"
  }
  "Export" {
    New-Item -ItemType Directory -Force -Path $exportDir | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $out = Join-Path $exportDir "owner-notes-$stamp.txt"
    @"
P02-USB-HF1 owner export (redacted)
utc=$([DateTime]::UtcNow.ToString('o'))
port=$Port
data_dir=$dataDir
gates_blocked=USB_WINDOWS_PHYSICAL,USB_STABILITY_30_MIN,USB_CAMERA_LAB_OWNER_SIGN,FACE_PILOT,INSTALLER,PRODUCTION_READY
do_not_include=frames,embeddings,pnp_raw,cookies,hmac,admin_password,sqlite
"@ | Out-File -FilePath $out -Encoding utf8
    Write-Log "Export notes: $out (fill measurements manually; no faces)"
  }
}
