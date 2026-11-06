#Requires -Version 5.1
<#
.SYNOPSIS
  P02-USB-HF3 isolated candidate on 127.0.0.1:18878 — Prepare/Preflight/Start/Stop/Diagnose/SafeExport.
  Native DirectShow COM enum (comtypes). NEVER touches 18876/18877 DataDirs or secrets.

.EXAMPLE
  .\p02_usb_hf3_candidate_18878.ps1 -Mode Prepare -FullSourceZip C:\path\FULL.zip -ExpectedSha256 <hex> -ModelsSourceDir C:\path\weights
  .\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
  .\p02_usb_hf3_candidate_18878.ps1 -Mode Start
  .\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
  .\p02_usb_hf3_candidate_18878.ps1 -Mode Stop
  .\p02_usb_hf3_candidate_18878.ps1 -Mode SafeExport
#>
param(
  [ValidateSet("Prepare", "Preflight", "Start", "Stop", "Diagnose", "SafeExport", "Export")]
  [string]$Mode = "Preflight",
  [string]$CandidateRoot = "$env:LOCALAPPDATA\MyPC.Attendance\p02-usb-hf3-candidate",
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

function Find-RepoRoot([string]$BackendDir) {
  $cand = Split-Path $BackendDir -Parent
  if (Test-Path (Join-Path $cand "models\manifest.json")) { return $cand }
  $up = Split-Path $cand -Parent
  if (Test-Path (Join-Path $up "MyPC.Attendance\models\manifest.json")) {
    return (Join-Path $up "MyPC.Attendance")
  }
  return $cand
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

function Invoke-VenvPip([string]$VenvPy, [string[]]$PipArgs) {
  & $VenvPy -m pip @PipArgs
  if ($LASTEXITCODE -ne 0) {
    throw ("pip failed exit={0} args={1}" -f $LASTEXITCODE, ($PipArgs -join ' '))
  }
}

function Resolve-ManifestPath([string]$SrcDir, [string]$ModelsSourceDir, [string]$CandidateRoot) {
  $candidates = @(
    (Join-Path $SrcDir "MyPC.Attendance\models\manifest.json"),
    (Join-Path $SrcDir "models\manifest.json")
  )
  $backend = $null
  try { $backend = Find-BackendDir $SrcDir } catch {}
  if ($backend) {
    $repo = Find-RepoRoot $backend
    $candidates += (Join-Path $repo "models\manifest.json")
  }
  if ($ModelsSourceDir) {
    $candidates += (Join-Path $ModelsSourceDir "..\manifest.json")
    $candidates += (Join-Path (Split-Path $ModelsSourceDir -Parent) "manifest.json")
  }
  $candidates += (Join-Path $CandidateRoot "models\manifest.json")
  foreach ($c in $candidates) {
    $full = [System.IO.Path]::GetFullPath($c)
    if (Test-Path $full) { return $full }
  }
  return $null
}

function Get-ManifestPinMap([string]$ManifestPath) {
  # Returns hashtable filename -> sha256 from models[] array OR flat object
  $map = @{}
  if (-not $ManifestPath -or -not (Test-Path $ManifestPath)) { return $map }
  $json = Get-Content $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($json.models) {
    foreach ($m in $json.models) {
      if ($m.filename -and $m.sha256) {
        $map[[string]$m.filename] = ([string]$m.sha256).ToLowerInvariant()
      }
    }
  } else {
    foreach ($p in $json.PSObject.Properties) {
      if ($p.Name -match '\.onnx$' -and $p.Value) {
        $map[$p.Name] = ([string]$p.Value).ToLowerInvariant()
      }
    }
  }
  return $map
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

if ($Mode -eq "Export") { $Mode = "SafeExport" }

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
    if (-not (Test-Path $venvDir)) {
      & $py -m venv $venvDir
      if ($LASTEXITCODE -ne 0) { throw "venv create failed" }
    } else {
      Write-Log "Reusing existing venv at $venvDir (no wipe)"
    }
    $venvPy = Join-Path $venvDir "Scripts\python.exe"
    if (-not (Test-Path $venvPy)) { throw "venv python missing at $venvPy" }

    # Prefer python -m pip (avoids pip.exe self-upgrade path quirks)
    try {
      Invoke-VenvPip $venvPy @("install", "--upgrade", "pip")
    } catch {
      Write-Log ("WARN: pip upgrade skipped/failed: {0}" -f $_.Exception.Message)
    }

    $backend = Find-BackendDir $srcDir
    $req = Join-Path $backend "requirements.txt"
    $reqWin = Join-Path $backend "requirements-windows.txt"
    if (-not (Test-Path $req)) { throw "requirements.txt missing: $req" }
    Invoke-VenvPip $venvPy @("install", "-r", $req)
    if (Test-Path $reqWin) {
      Invoke-VenvPip $venvPy @("install", "-r", $reqWin)
      Write-Log "Installed requirements-windows.txt (pywin32/WMI/comtypes)"
    } else {
      throw "requirements-windows.txt missing — refuse Prepare without COM enum deps"
    }

    $manifestPath = Resolve-ManifestPath $srcDir $ModelsSourceDir $CandidateRoot
    if (-not $manifestPath) {
      throw "models/manifest.json not found — refuse silent model install"
    }
    Write-Log "Using manifest: $manifestPath"
    $pins = Get-ManifestPinMap $manifestPath
    if ($pins.Count -lt 2) {
      throw "manifest must pin at least YuNet + SFace ONNX filenames"
    }

    if (-not $ModelsSourceDir -or -not (Test-Path $ModelsSourceDir)) {
      throw "Prepare requires -ModelsSourceDir with existing ONNX weights (owner already has PIN_MATCH models — do not redownload)"
    }
    $required = @(
      "face_detection_yunet_2023mar.onnx",
      "face_recognition_sface_2021dec.onnx"
    )
    foreach ($name in $required) {
      if (-not $pins.ContainsKey($name)) { throw "manifest missing pin for $name" }
      $srcFile = Join-Path $ModelsSourceDir $name
      if (-not (Test-Path $srcFile)) { throw "Missing weight file: $srcFile" }
      $dst = Join-Path $modelsDir $name
      Copy-Item $srcFile -Destination $dst -Force
      $sha = Get-Sha256Lower $dst
      $exp = $pins[$name]
      if ($sha -ne $exp) {
        throw "MODEL PIN_MISMATCH $name got=$sha expected=$exp"
      }
      Write-Log ("PIN_MATCH model {0} sha={1}" -f $name, $sha)
    }
    Write-Log "MODEL_PINS_PASS=true"
    Write-Log "Prepare OK — DataDir=$dataDir models=$modelsDir venv=$venvDir"
  }
  "Preflight" {
    Write-Log "Preflight port=$Port candidate=$CandidateRoot"
    $venvPy = Join-Path $venvDir "Scripts\python.exe"
    if (-not (Test-Path $venvPy)) { throw "venv missing — run Prepare first" }
    & $venvPy -c "import fastapi,uvicorn,cv2,comtypes; print('deps-ok', fastapi.__version__, cv2.__version__, comtypes.__version__)"
    if ($LASTEXITCODE -ne 0) { throw "Preflight import failed" }
    $backend = Find-BackendDir $srcDir
    if (-not (Test-Path (Join-Path $backend "app\main.py"))) { throw "backend layout invalid" }
    $busy = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($busy) { Write-Log "WARN: port $Port in use" } else { Write-Log "Port $Port free" }
    foreach ($name in @("face_detection_yunet_2023mar.onnx","face_recognition_sface_2021dec.onnx")) {
      if (-not (Test-Path (Join-Path $modelsDir $name))) { throw "Preflight missing model $name" }
    }
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
      } catch {}
    }
    if (-not $ok) {
      Write-Log "HEALTH failed — see $errLog"
      throw "Backend did not become healthy on 127.0.0.1:$Port"
    }
    Write-Log "Start OK — open http://127.0.0.1:$Port"
  }
  "Stop" {
    if (Test-Path $pidFile) {
      $old = Get-Content $pidFile -ErrorAction SilentlyContinue
      if ($old) {
        try { Stop-Process -Id ([int]$old) -Force -ErrorAction SilentlyContinue } catch {}
        Write-Log "Stopped pid=$old"
      }
      Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    } else {
      Write-Log "No pid file — nothing to stop"
    }
  }
  "Diagnose" {
    $venvPy = Join-Path $venvDir "Scripts\python.exe"
    if (-not (Test-Path $venvPy)) { throw "venv missing — run Prepare first" }
    $backend = Find-BackendDir $srcDir
    $diagPy = Join-Path (Split-Path $backend -Parent) "scripts\windows\p02_usb_hf3_readonly_diag.py"
    # Prefer packaged script next to this ps1, then under src tree
    $localDiag = Join-Path $PSScriptRoot "p02_usb_hf3_readonly_diag.py"
    if (Test-Path $localDiag) { $diagPy = $localDiag }
    else {
      $alt = Get-ChildItem -Path $srcDir -Recurse -Filter "p02_usb_hf3_readonly_diag.py" -ErrorAction SilentlyContinue |
        Select-Object -First 1
      if ($alt) { $diagPy = $alt.FullName }
    }
    if (-not (Test-Path $diagPy)) { throw "readonly diag script missing" }
    $env:MYPC_MODELS_DIR = $modelsDir
    $env:PYTHONPATH = $backend
    Write-Log "Running read-only USB diag (no admin required)"
    & $venvPy $diagPy --models-dir $modelsDir
    if ($LASTEXITCODE -ne 0) { throw "Diagnose failed exit=$LASTEXITCODE" }
  }
  "SafeExport" {
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
P02-USB-HF3 owner SafeExport (redacted)
utc=$([DateTime]::UtcNow.ToString('o'))
port=$Port
candidate_root=$CandidateRoot
health=$health
gates_blocked=USB_WINDOWS_PHYSICAL,USB_STABILITY_30_MIN,USB_CAMERA_LAB_OWNER_SIGN,FACE_PILOT,INSTALLER,PRODUCTION_READY
excluded=frames,embeddings,pnp_raw,device_path_raw,cookies,hmac,admin_password,sqlite,secrets,uvicorn_full_logs
"@ | Out-File -FilePath $notes -Encoding utf8
    if (Test-Path (Join-Path $CandidateRoot "logs\candidate.log")) {
      # Keep only last 100 lines of candidate log (already redacted statuses)
      Get-Content (Join-Path $CandidateRoot "logs\candidate.log") -Tail 100 |
        Out-File (Join-Path $stage "candidate-tail.log") -Encoding utf8
    }
    if (Test-Path (Join-Path $CandidateRoot "logs\diag-redacted.json")) {
      Copy-Item (Join-Path $CandidateRoot "logs\diag-redacted.json") (Join-Path $stage "diag-redacted.json") -Force
    }
    $zipOut = Join-Path $exportDir "p02-usb-hf3-safe-export-$stamp.zip"
    if (Test-Path $zipOut) { Remove-Item $zipOut -Force }
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zipOut -Force
    Write-Log ("SafeExport ZIP={0} sha={1}" -f $zipOut, (Get-Sha256Lower $zipOut))
  }
}
