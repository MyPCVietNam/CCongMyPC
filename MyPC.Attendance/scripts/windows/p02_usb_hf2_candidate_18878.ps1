#Requires -Version 5.1
<#
.SYNOPSIS
  P02-USB-HF2 isolated candidate on 127.0.0.1:18878 — Prepare/Preflight/Start/Export.
  Actually launches uvicorn. NEVER touches 18876/18877 DataDirs or secrets.

.EXAMPLE
  .\p02_usb_hf2_candidate_18878.ps1 -Mode Prepare -FullSourceZip C:\path\FULL.zip -ExpectedSha256 <hex>
  .\p02_usb_hf2_candidate_18878.ps1 -Mode Preflight
  .\p02_usb_hf2_candidate_18878.ps1 -Mode Start
  .\p02_usb_hf2_candidate_18878.ps1 -Mode Export
#>
param(
  [ValidateSet("Prepare", "Preflight", "Start", "Export")]
  [string]$Mode = "Preflight",
  [string]$CandidateRoot = "$env:LOCALAPPDATA\MyPC.Attendance\p02-usb-hf2-candidate",
  [string]$FullSourceZip = "",
  [string]$ExpectedSha256 = "",
  [string]$ModelsSourceDir = "",
  [int]$Port = 18878,
  [string]$PythonExe = "py"
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
}

function Get-Sha256Lower([string]$Path) {
  return (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Find-BackendDir([string]$Root) {
  $direct = Join-Path $Root "MyPC.Attendance\backend"
  if (Test-Path (Join-Path $direct "app\main.py")) { return $direct }
  $hit = Get-ChildItem -Path $Root -Recurse -Filter "main.py" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match '[\\/]app[\\/]main\.py$' } |
    Select-Object -First 1
  if ($hit) { return $hit.Directory.Parent.FullName }
  throw "backend app/main.py not found under $Root — run Prepare first"
}

function Find-Python312 {
  $candidates = @()
  try { $candidates += & $PythonExe -3.12 -c "import sys; print(sys.executable)" 2>$null } catch {}
  try { $candidates += & python -c "import sys; print(sys.executable)" 2>$null } catch {}
  foreach ($c in $candidates) {
    if ($c -and (Test-Path $c)) { return $c.Trim() }
  }
  throw "Python 3.12 executable not found. Install Python 3.12 and retry."
}

Assert-PortSafe
New-Item -ItemType Directory -Force -Path $CandidateRoot | Out-Null
$dataDir = Join-Path $CandidateRoot "DataDir"
$srcDir = Join-Path $CandidateRoot "src"
$venvDir = Join-Path $CandidateRoot "venv"
$modelsDir = Join-Path $CandidateRoot "models\weights"
$exportDir = Join-Path $CandidateRoot "export"
$pidFile = Join-Path $CandidateRoot "uvicorn.pid"
$outLog = Join-Path $CandidateRoot "logs\uvicorn.out.log"
$errLog = Join-Path $CandidateRoot "logs\uvicorn.err.log"

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
    New-Item -ItemType Directory -Force -Path $modelsDir | Out-Null

    $py = Find-Python312
    Write-Log "Using Python: $py"
    if (Test-Path $venvDir) { Remove-Item -Recurse -Force $venvDir }
    & $py -m venv $venvDir
    $pip = Join-Path $venvDir "Scripts\pip.exe"
    $venvPy = Join-Path $venvDir "Scripts\python.exe"
    if (-not (Test-Path $pip)) { throw "venv pip missing at $pip" }

    $backend = Find-BackendDir $srcDir
    $req = Join-Path $backend "requirements.txt"
    $reqWin = Join-Path $backend "requirements-windows.txt"
    if (-not (Test-Path $req)) { throw "requirements.txt missing: $req" }
    # Prefer python -m pip (avoids pip.exe self-upgrade CO_E / path quirks on Win)
    & $venvPy -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { Write-Log "WARN: pip upgrade failed exit=$LASTEXITCODE — continuing" }
    & $venvPy -m pip install -r $req
    if ($LASTEXITCODE -ne 0) { throw "pip install requirements.txt failed" }
    if (Test-Path $reqWin) {
      & $venvPy -m pip install -r $reqWin
      if ($LASTEXITCODE -ne 0) { throw "pip install requirements-windows.txt failed" }
      Write-Log "Installed requirements-windows.txt (pywin32/WMI/comtypes)"
    } else {
      Write-Log "WARN: requirements-windows.txt missing — USB PnP linkage may stay unverified"
    }

    # Copy ONLY .onnx weights with optional manifest PIN_MATCH
    if ($ModelsSourceDir -and (Test-Path $ModelsSourceDir)) {
      $manifest = $null
      foreach ($cand in @(
          (Join-Path $srcDir "MyPC.Attendance\models\manifest.json"),
          (Join-Path $ModelsSourceDir "..\manifest.json"),
          (Join-Path $CandidateRoot "models\manifest.json")
        )) {
        if (Test-Path $cand) { $manifest = Get-Content $cand -Raw | ConvertFrom-Json; break }
      }
      Get-ChildItem $ModelsSourceDir -Filter "*.onnx" | ForEach-Object {
        $dst = Join-Path $modelsDir $_.Name
        Copy-Item $_.FullName -Destination $dst -Force
        $sha = Get-Sha256Lower $dst
        if ($manifest -and $manifest.PSObject.Properties.Name -contains $_.Name) {
          $exp = [string]$manifest.($_.Name)
          if ($exp -and $exp.ToLowerInvariant() -ne $sha) {
            throw "Model SHA256 mismatch for $($_.Name): got $sha expected $exp"
          }
          Write-Log ("PIN_MATCH model {0} sha={1}" -f $_.Name, $sha)
        } else {
          Write-Log ("Copied model {0} sha={1} (no manifest pin found — owner must verify)" -f $_.Name, $sha)
        }
      }
    }
    Write-Log "Prepare OK — DataDir=$dataDir models=$modelsDir venv=$venvDir"
  }
  "Preflight" {
    Write-Log "Preflight port=$Port candidate=$CandidateRoot"
    $venvPy = Join-Path $venvDir "Scripts\python.exe"
    if (-not (Test-Path $venvPy)) { throw "venv missing — run Prepare first" }
    & $venvPy -c "import fastapi,uvicorn,cv2; print('deps-ok', fastapi.__version__, cv2.__version__)"
    $backend = Find-BackendDir $srcDir
    if (-not (Test-Path (Join-Path $backend "app\main.py"))) { throw "backend layout invalid" }
    $busy = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($busy) { Write-Log "WARN: port $Port in use" } else { Write-Log "Port $Port free" }
    if (-not (Test-Path $modelsDir)) { Write-Log "WARN: models dir missing — face overlay may be blocked" }
    Write-Log "Preflight OK"
  }
  "Start" {
    $venvPy = Join-Path $venvDir "Scripts\python.exe"
    if (-not (Test-Path $venvPy)) { throw "venv missing — run Prepare first" }
    $backend = Find-BackendDir $srcDir
    New-Item -ItemType Directory -Force -Path (Split-Path $outLog) | Out-Null
    if (Test-Path $pidFile) {
      $old = Get-Content $pidFile -ErrorAction SilentlyContinue
      if ($old) {
        try { Stop-Process -Id ([int]$old) -Force -ErrorAction SilentlyContinue } catch {}
      }
      Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
    $env:MYPC_DATA_DIR = $dataDir
    $env:DATA_DIR = $dataDir
    $env:MYPC_MODELS_DIR = $modelsDir
    Write-Log "Starting uvicorn cwd=$backend DATA_DIR=$dataDir MODELS_DIR=$modelsDir bind=127.0.0.1:$Port"
    $argList = @(
      "-m", "uvicorn", "app.main:app",
      "--host", "127.0.0.1",
      "--port", "$Port",
      "--app-dir", $backend
    )
    $proc = Start-Process -FilePath $venvPy -ArgumentList $argList `
      -WorkingDirectory $backend `
      -RedirectStandardOutput $outLog `
      -RedirectStandardError $errLog `
      -PassThru -WindowStyle Hidden
    Set-Content -Path $pidFile -Value $proc.Id -Encoding ASCII
    Write-Log "uvicorn pid=$($proc.Id) — waiting for health"
    $ok = $false
    for ($i = 0; $i -lt 40; $i++) {
      Start-Sleep -Seconds 1
      try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/v1/health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) {
          Write-Log ("HEALTH status={0}" -f $r.StatusCode)
          $ok = $true
          break
        }
      } catch {
        # keep waiting
      }
    }
    if (-not $ok) {
      Write-Log "HEALTH failed — see $errLog"
      throw "Backend did not become healthy on 127.0.0.1:$Port"
    }
    Write-Log "Start OK — open http://127.0.0.1:$Port (footer MyPC Việt Nam https://mypc.vn)"
  }
  "Export" {
    New-Item -ItemType Directory -Force -Path $exportDir | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $stage = Join-Path $exportDir "stage-$stamp"
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    $notes = Join-Path $stage "owner-status.txt"
    $health = "UNAVAILABLE"
    try {
      $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/v1/health" -UseBasicParsing -TimeoutSec 3
      $health = "HTTP_" + $r.StatusCode
    } catch { $health = "ERROR" }
    @"
P02-USB-HF2 owner export (redacted)
utc=$([DateTime]::UtcNow.ToString('o'))
port=$Port
data_dir=$dataDir
models_dir=$modelsDir
health=$health
gates_blocked=USB_WINDOWS_PHYSICAL,USB_STABILITY_30_MIN,USB_CAMERA_LAB_OWNER_SIGN,FACE_PILOT,INSTALLER,PRODUCTION_READY
excluded=frames,embeddings,pnp_raw,cookies,hmac,admin_password,sqlite,secrets
"@ | Out-File -FilePath $notes -Encoding utf8
    if (Test-Path (Join-Path $CandidateRoot "logs\candidate.log")) {
      Copy-Item (Join-Path $CandidateRoot "logs\candidate.log") (Join-Path $stage "candidate.log") -Force
    }
    # Redact-ish: copy only last 200 lines of uvicorn logs
    foreach ($lf in @($outLog, $errLog)) {
      if (Test-Path $lf) {
        Get-Content $lf -Tail 200 | Out-File (Join-Path $stage (Split-Path $lf -Leaf)) -Encoding utf8
      }
    }
    $zipOut = Join-Path $exportDir "p02-usb-hf2-export-$stamp.zip"
    if (Test-Path $zipOut) { Remove-Item $zipOut -Force }
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zipOut -Force
    Write-Log ("Export ZIP={0} sha={1}" -f $zipOut, (Get-Sha256Lower $zipOut))
  }
}
