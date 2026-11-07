#Requires -Version 5.1
<#
.SYNOPSIS
  P02-USB-HF3 isolated candidate on 127.0.0.1:18878 — Prepare/Update/Preflight/Start/Stop/Diagnose/SafeExport.
  Native DirectShow COM enum (comtypes). NEVER touches 18876/18877 DataDirs or secrets.

.EXAMPLE
  .\p02_usb_hf3_candidate_18878.ps1 -Mode Prepare -FullSourceZip C:\path\FULL.zip -ExpectedSha256 <hex> -ModelsSourceDir C:\path\weights
  .\p02_usb_hf3_candidate_18878.ps1 -Mode Update -FullSourceZip C:\path\FULL.zip -ExpectedSha256 <hex>
  .\p02_usb_hf3_candidate_18878.ps1 -Mode Preflight
  .\p02_usb_hf3_candidate_18878.ps1 -Mode Diagnose
  .\p02_usb_hf3_candidate_18878.ps1 -Mode Start
  .\p02_usb_hf3_candidate_18878.ps1 -Mode Stop
  .\p02_usb_hf3_candidate_18878.ps1 -Mode SafeExport
#>
param(
  [ValidateSet("Prepare", "Update", "Preflight", "Start", "Stop", "Diagnose", "SafeExport", "Export")]
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

# --- HF3 PID ownership (venv redirector → real python.exe child) ---
# Trust model: HTTP 200 alone never proves ownership. Accept listener owned by
# launcher OR a verified python.exe descendant with exact uvicorn cmdline.
# conhost.exe is NEVER a server. Persist listener PID + CreationDate + nonce.

function Get-Win32ProcessById([int]$ProcessId) {
  if ($ProcessId -le 0) { return $null }
  return Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $ProcessId) -ErrorAction SilentlyContinue
}

function Split-Hf3WindowsCommandLine([string]$CommandLine) {
  # CommandLineToArgvW-style split for ownership checks (quotes + spaces).
  if (-not $CommandLine) { return @() }
  $argsOut = New-Object System.Collections.Generic.List[string]
  $cur = New-Object System.Text.StringBuilder
  $inQuotes = $false
  $i = 0
  $n = $CommandLine.Length
  while ($i -lt $n) {
    $ch = $CommandLine[$i]
    if ($ch -eq [char]'\') {
      $bs = 0
      while ($i -lt $n -and $CommandLine[$i] -eq [char]'\') { $bs++; $i++ }
      if ($i -lt $n -and $CommandLine[$i] -eq [char]'"') {
        for ($k = 0; $k -lt [math]::Floor($bs / 2); $k++) { [void]$cur.Append('\') }
        if (($bs % 2) -eq 1) {
          [void]$cur.Append('"')
          $i++
        } else {
          $inQuotes = -not $inQuotes
          $i++
        }
      } else {
        for ($k = 0; $k -lt $bs; $k++) { [void]$cur.Append('\') }
      }
      continue
    }
    if ($ch -eq [char]'"') {
      $inQuotes = -not $inQuotes
      $i++
      continue
    }
    if ((($ch -eq [char]' ') -or ($ch -eq [char]"`t")) -and -not $inQuotes) {
      if ($cur.Length -gt 0) {
        $argsOut.Add($cur.ToString()) | Out-Null
        $cur.Length = 0
      }
      $i++
      continue
    }
    [void]$cur.Append($ch)
    $i++
  }
  if ($cur.Length -gt 0) { $argsOut.Add($cur.ToString()) | Out-Null }
  return ,@($argsOut.ToArray())
}

function Get-Hf3OptionValues([string[]]$Argv, [string]$Name) {
  $out = New-Object System.Collections.Generic.List[string]
  $key = $Name.ToLowerInvariant()
  $i = 0
  while ($i -lt $Argv.Count) {
    $a = [string]$Argv[$i]
    $al = $a.ToLowerInvariant()
    if ($al -eq $key) {
      if ($i + 1 -ge $Argv.Count) { $out.Add("__MISSING__") | Out-Null; break }
      $out.Add([string]$Argv[$i + 1]) | Out-Null
      $i += 2
      continue
    }
    if ($al.StartsWith($key + "=")) {
      $out.Add($a.Substring($key.Length + 1)) | Out-Null
      $i++
      continue
    }
    $i++
  }
  return ,@($out.ToArray())
}

function Test-Hf3UvicornCommandLine {
  param(
    [string]$CommandLine,
    [string]$Backend,
    [int]$PortNum,
    [string]$HostAddr = "127.0.0.1"
  )
  if (-not $CommandLine) { return $false }
  $argv = @(Split-Hf3WindowsCommandLine $CommandLine)
  if ($argv.Count -lt 5) { return $false }
  # Reject -c / --reload / --workers — not HF3 uvicorn interpreter entrypoints.
  foreach ($tok in $argv) {
    $tl = ([string]$tok).ToLowerInvariant()
    if ($tl -eq "-c" -or $tl.StartsWith("-c") -or $tl -eq "--reload" -or $tl -eq "--workers") {
      return $false
    }
  }
  # Require contiguous interpreter entry: [safeFlags*] -m uvicorn app.main:app (never -m anywhere).
  $safeNoVal = @("-b", "-bb", "-B", "-E", "-I", "-O", "-OO", "-s", "-S", "-u", "-v", "-x")
  $pos = 1
  $entryOk = $false
  while ($pos -lt $argv.Count) {
    $cur = ([string]$argv[$pos]).ToLowerInvariant()
    if ($cur -eq "-m") {
      if (($pos + 2) -lt $argv.Count -and
          ([string]$argv[$pos + 1]).ToLowerInvariant() -eq "uvicorn" -and
          [string]$argv[$pos + 2] -eq "app.main:app") {
        $entryOk = $true
      }
      break
    }
    if ($safeNoVal -contains $cur) { $pos++; continue }
    break
  }
  if (-not $entryOk) { return $false }
  $hosts = @(Get-Hf3OptionValues $argv "--host")
  $ports = @(Get-Hf3OptionValues $argv "--port")
  $appDirs = @(Get-Hf3OptionValues $argv "--app-dir")
  if ($hosts.Count -ne 1 -or $hosts[0] -eq "__MISSING__") { return $false }
  if ($ports.Count -ne 1 -or $ports[0] -eq "__MISSING__") { return $false }
  if ($appDirs.Count -ne 1 -or $appDirs[0] -eq "__MISSING__") { return $false }
  if ([string]$hosts[0] -ne $HostAddr) { return $false }
  if ([string]$ports[0] -ne "$PortNum") { return $false }
  $backendNorm = (($Backend -replace '/', '\').TrimEnd('\')).ToLowerInvariant()
  if (-not $backendNorm) { return $false }
  $appNorm = (([string]$appDirs[0] -replace '/', '\').TrimEnd('\')).ToLowerInvariant()
  # Exact canonical --app-dir value only — never IndexOf/substring anywhere in cmdline.
  if ($appNorm -ne $backendNorm) { return $false }
  return $true
}

function Test-IsPythonProcessName([string]$Name) {
  $n = ([string]$Name).ToLowerInvariant()
  return @("python.exe", "python", "pythonw.exe", "pythonw") -contains $n
}

function Test-IsConhostName([string]$Name) {
  $n = ([string]$Name).ToLowerInvariant()
  return @("conhost.exe", "conhost") -contains $n
}

function Test-IsProcessDescendantOf {
  param([int]$ChildPid, [int]$AncestorPid, [int]$MaxDepth = 8)
  if ($ChildPid -le 0 -or $AncestorPid -le 0) { return $false }
  if ($ChildPid -eq $AncestorPid) { return $true }
  $cur = $ChildPid
  $seen = @{}
  for ($i = 0; $i -lt $MaxDepth; $i++) {
    if ($seen.ContainsKey("$cur")) { return $false }
    $seen["$cur"] = $true
    $p = Get-Win32ProcessById $cur
    if (-not $p) { return $false }
    $pp = [int]$p.ParentProcessId
    if ($pp -eq $AncestorPid) { return $true }
    if ($pp -le 0) { return $false }
    $cur = $pp
  }
  return $false
}

function Get-Hf3PortListenerOwnerPids([int]$PortNum) {
  $ls = @(Get-NetTCPConnection -LocalPort $PortNum -State Listen -ErrorAction SilentlyContinue)
  return @($ls | ForEach-Object { [int]$_.OwningProcess } | Select-Object -Unique)
}

function Resolve-Hf3ListenerOwnership {
  param(
    [int]$LauncherPid,
    [string]$Backend,
    [int]$PortNum,
    [string]$HostAddr = "127.0.0.1"
  )
  $owners = @(Get-Hf3PortListenerOwnerPids $PortNum)
  if ($owners.Count -eq 0) {
    return [pscustomobject]@{
      Relationship = "NONE"; ListenerPid = 0; Reason = "no_listener"; ListenerCreation = ""
    }
  }
  if ($owners.Count -gt 1) {
    return [pscustomobject]@{
      Relationship = "AMBIGUOUS"; ListenerPid = 0; Reason = "multiple_listener_owners"; ListenerCreation = ""
    }
  }
  $listenerPid = [int]$owners[0]
  $listener = Get-Win32ProcessById $listenerPid
  if (-not $listener) {
    return [pscustomobject]@{
      Relationship = "UNVERIFIED"; ListenerPid = 0; Reason = "listener_process_missing"; ListenerCreation = ""
    }
  }
  if (Test-IsConhostName $listener.Name) {
    return [pscustomobject]@{
      Relationship = "UNVERIFIED"; ListenerPid = 0; Reason = "listener_is_conhost"; ListenerCreation = ""
    }
  }
  $cmd = [string]$listener.CommandLine
  if (-not (Test-Hf3UvicornCommandLine -CommandLine $cmd -Backend $Backend -PortNum $PortNum -HostAddr $HostAddr)) {
    return [pscustomobject]@{
      Relationship = "UNVERIFIED"; ListenerPid = 0; Reason = "listener_cmdline_mismatch"; ListenerCreation = ""
    }
  }
  $creation = ""
  try { $creation = ([datetime]$listener.CreationDate).ToUniversalTime().ToString("o") } catch { $creation = [string]$listener.CreationDate }

  if ($listenerPid -eq $LauncherPid) {
    # DIRECT still requires a Python process identity (mirrors hf3_pid_ownership.py).
    if (Test-IsPythonProcessName $listener.Name) {
      return [pscustomobject]@{
        Relationship = "DIRECT"; ListenerPid = $listenerPid; Reason = "listener_pid_equals_launcher"; ListenerCreation = $creation
      }
    }
    return [pscustomobject]@{
      Relationship = "UNVERIFIED"; ListenerPid = 0; Reason = "direct_not_python"; ListenerCreation = ""
    }
  }
  if (-not (Test-IsPythonProcessName $listener.Name)) {
    return [pscustomobject]@{
      Relationship = "UNVERIFIED"; ListenerPid = 0; Reason = "descendant_not_python"; ListenerCreation = ""
    }
  }
  if (-not (Test-IsProcessDescendantOf -ChildPid $listenerPid -AncestorPid $LauncherPid)) {
    return [pscustomobject]@{
      Relationship = "UNVERIFIED"; ListenerPid = 0; Reason = "not_in_launcher_tree"; ListenerCreation = ""
    }
  }
  $launcher = Get-Win32ProcessById $LauncherPid
  if ($launcher) {
    $lCreate = ""
    try { $lCreate = ([datetime]$launcher.CreationDate).ToUniversalTime().ToString("o") } catch { $lCreate = [string]$launcher.CreationDate }
    if ($lCreate -and $creation -and ($creation -lt $lCreate)) {
      return [pscustomobject]@{
        Relationship = "UNVERIFIED"; ListenerPid = 0; Reason = "listener_creation_before_launcher"; ListenerCreation = ""
      }
    }
  }
  return [pscustomobject]@{
    Relationship = "VERIFIED_DESCENDANT"; ListenerPid = $listenerPid; Reason = "python_descendant_with_uvicorn_cmdline"; ListenerCreation = $creation
  }
}

function Test-Hf3HealthStartPass([int]$StatusCode, [string]$Body) {
  if ($StatusCode -ne 200) { return $false }
  if (-not $Body) { return $false }
  try {
    $obj = $Body | ConvertFrom-Json
  } catch {
    return $false
  }
  # Top-level fields only — nested status/startup_phase must not satisfy Start.
  $topStatus = [string]$obj.status
  $topPhase = [string]$obj.startup_phase
  if ($topStatus -ne "ok") { return $false }
  if ($topPhase -ne "READY") { return $false }
  return $true
}

function Save-Hf3LaunchMeta {
  param(
    [string]$Path,
    [hashtable]$Meta
  )
  ($Meta | ConvertTo-Json -Depth 6) | Set-Content -Path $Path -Encoding UTF8
}

function Read-Hf3LaunchMeta([string]$Path) {
  if (-not (Test-Path $Path)) { return $null }
  try {
    return (Get-Content $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
  } catch {
    return $null
  }
}

function Test-Hf3LaunchMetaSchema($Meta) {
  if (-not $Meta) { return $false }
  if ([string]$Meta.schema -ne "mypc.hf3.launch.v1") { return $false }
  if ([int]$Meta.port -ne 18878) { return $false }
  if (-not [string]$Meta.backend) { return $false }
  if (-not [string]$Meta.listener_creation) { return $false }
  if ([int]$Meta.listener_pid -le 0) { return $false }
  return $true
}

function Test-LiveMatchesLaunchMeta {
  param($Meta, [int]$LivePid)
  if (-not (Test-Hf3LaunchMetaSchema $Meta)) { return $false }
  if ($LivePid -le 0 -or [int]$Meta.listener_pid -ne $LivePid) { return $false }
  $live = Get-Win32ProcessById $LivePid
  if (-not $live) { return $false }
  if (Test-IsConhostName $live.Name) { return $false }
  $liveCreate = ""
  try { $liveCreate = ([datetime]$live.CreationDate).ToUniversalTime().ToString("o") } catch { $liveCreate = [string]$live.CreationDate }
  # Fail closed: blank stored or live creation never authenticates.
  if (-not [string]$Meta.listener_creation) { return $false }
  if (-not $liveCreate) { return $false }
  if ($liveCreate -ne [string]$Meta.listener_creation) { return $false }
  if (-not (Test-Hf3UvicornCommandLine -CommandLine ([string]$live.CommandLine) -Backend ([string]$Meta.backend) -PortNum ([int]$Meta.port))) {
    return $false
  }
  return $true
}

function Stop-VerifiedHf3Identity {
  <#
    .SYNOPSIS
      Kill exactly one process only when PID + required creation timestamp + role proof match.
      Never uses PowerShell automatic $PID. Never authorizes via candidate-folder substring.
  #>
  param(
    [int]$TargetPid,
    [string]$ExpectedCreation,
    [string]$Backend,
    [int]$PortNum,
    [ValidateSet("listener", "launcher")]
    [string]$Role,
    [string]$ExpectedExePath = ""
  )
  if ($TargetPid -le 0) {
    Write-Log "Refusing kill — invalid TargetPid"
    return $false
  }
  if (-not $ExpectedCreation) {
    Write-Log ("Refusing kill pid={0} role={1} — missing required creation timestamp" -f $TargetPid, $Role)
    return $false
  }
  $procInfo = Get-Win32ProcessById $TargetPid
  if (-not $procInfo) {
    Write-Log ("Stop identity: pid={0} already absent" -f $TargetPid)
    return $true
  }
  if (Test-IsConhostName $procInfo.Name) {
    Write-Log ("Refusing to kill conhost pid={0}" -f $TargetPid)
    return $false
  }
  $liveCreate = ""
  try { $liveCreate = ([datetime]$procInfo.CreationDate).ToUniversalTime().ToString("o") } catch { $liveCreate = [string]$procInfo.CreationDate }
  if (-not $liveCreate -or $liveCreate -ne $ExpectedCreation) {
    Write-Log ("Refusing to kill pid={0} — creation-time mismatch/absent (possible PID reuse)" -f $TargetPid)
    return $false
  }
  $cmd = [string]$procInfo.CommandLine
  if ($Role -eq "listener") {
    if (-not (Test-Hf3UvicornCommandLine -CommandLine $cmd -Backend $Backend -PortNum $PortNum)) {
      Write-Log ("Refusing to kill pid={0} — listener cmdline proof failed" -f $TargetPid)
      return $false
    }
  } else {
    # launcher: must be python AND match expected venv executable path (not folder substring)
    if (-not (Test-IsPythonProcessName $procInfo.Name)) {
      Write-Log ("Refusing to kill pid={0} — launcher not python" -f $TargetPid)
      return $false
    }
    $exe = [string]$procInfo.ExecutablePath
    if (-not $ExpectedExePath) {
      Write-Log ("Refusing to kill launcher pid={0} — ExpectedExePath missing" -f $TargetPid)
      return $false
    }
    $exeNorm = ($exe -replace '/', '\').TrimEnd('\')
    $expNorm = ($ExpectedExePath -replace '/', '\').TrimEnd('\')
    if (-not $exeNorm -or ($exeNorm.ToLowerInvariant() -ne $expNorm.ToLowerInvariant())) {
      # Also accept uvicorn cmdline if redirector was replaced by the real server (DIRECT case)
      if (-not (Test-Hf3UvicornCommandLine -CommandLine $cmd -Backend $Backend -PortNum $PortNum)) {
        Write-Log ("Refusing to kill launcher pid={0} — exe path mismatch and no uvicorn proof" -f $TargetPid)
        return $false
      }
    }
  }
  try {
    Stop-Process -Id $TargetPid -Force -ErrorAction Stop
    Write-Log ("Stopped verified pid={0} role={1} name={2}" -f $TargetPid, $Role, $procInfo.Name)
    return $true
  } catch {
    Write-Log ("Stop-Process failed pid={0}: {1}" -f $TargetPid, $_.Exception.Message)
    return $false
  }
}

function Stop-VerifiedHf3LaunchTree {
  param($Meta)
  if (-not (Test-Hf3LaunchMetaSchema $Meta)) {
    Write-Log "Stop tree refused — launch meta schema/identity incomplete"
    return $false
  }
  $backend = [string]$Meta.backend
  $portNum = [int]$Meta.port
  $okListener = Stop-VerifiedHf3Identity -TargetPid ([int]$Meta.listener_pid) `
    -ExpectedCreation ([string]$Meta.listener_creation) `
    -Backend $backend -PortNum $portNum -Role "listener"
  $okLauncher = $true
  if ([int]$Meta.launcher_pid -gt 0 -and [int]$Meta.launcher_pid -ne [int]$Meta.listener_pid) {
    if (-not [string]$Meta.launcher_creation) {
      Write-Log ("Refusing launcher kill pid={0} — launcher_creation missing; listener stop ok={1}" -f [int]$Meta.launcher_pid, $okListener)
      $okLauncher = $false
    } else {
      $okLauncher = Stop-VerifiedHf3Identity -TargetPid ([int]$Meta.launcher_pid) `
        -ExpectedCreation ([string]$Meta.launcher_creation) `
        -Backend $backend -PortNum $portNum -Role "launcher" `
        -ExpectedExePath ([string]$Meta.venv_python)
    }
  }
  return ($okListener -and $okLauncher)
}

Assert-PortSafe
New-Item -ItemType Directory -Force -Path $CandidateRoot | Out-Null
$dataDir = Join-Path $CandidateRoot "DataDir"
$srcDir = Join-Path $CandidateRoot "src"
$venvDir = Join-Path $CandidateRoot "venv"
$modelsDir = Join-Path $CandidateRoot "models\weights"
$exportDir = Join-Path $CandidateRoot "export"
$pidFile = Join-Path $CandidateRoot "uvicorn.pid"
$launchMetaFile = Join-Path $CandidateRoot "uvicorn.launch.json"
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
  "Update" {
    # Source-only refresh for an already-prepared HF3 candidate.
    # NEVER wipe DataDir, models/weights, or venv. NEVER touch 18876/18877.
    # PowerShell 5.1: Rename-Item -NewName must be a leaf name (same parent), not a path.
    if (-not $FullSourceZip -or -not (Test-Path $FullSourceZip)) {
      throw "Update requires -FullSourceZip pointing to FULL-SOURCE ZIP"
    }
    if (-not $ExpectedSha256) { throw "Update requires -ExpectedSha256 (lowercase hex)" }
    $venvPy = Join-Path $venvDir "Scripts\python.exe"
    if (-not (Test-Path $venvPy)) { throw "venv missing — run Prepare once before Update" }
    if (-not (Test-Path $dataDir)) { throw "DataDir missing — run Prepare first (Update will not create secrets)" }

    # Validate FULL-SOURCE SHA256 + staged layout BEFORE interrupting any running candidate.
    $got = Get-Sha256Lower $FullSourceZip
    if ($got -ne $ExpectedSha256.ToLowerInvariant()) {
      throw "SHA256 mismatch: got $got expected $($ExpectedSha256.ToLowerInvariant())"
    }
    Write-Log "Update SHA256 PIN_MATCH — staging source (DataDir/models/venv preserved)"

    $stageSrc = Join-Path $CandidateRoot "src-update-staging"
    if (Test-Path $stageSrc) { Remove-Item -Recurse -Force $stageSrc }
    New-Item -ItemType Directory -Force -Path $stageSrc | Out-Null
    Expand-Archive -Path $FullSourceZip -DestinationPath $stageSrc -Force

    # Validate staged backend layout BEFORE touching live src or stopping the server.
    $stagedBackend = $null
    try { $stagedBackend = Find-BackendDir $stageSrc } catch {
      Remove-Item -Recurse -Force $stageSrc -ErrorAction SilentlyContinue
      throw ("Update refused: staged ZIP missing backend app/main.py ({0})" -f $_.Exception.Message)
    }
    if (-not (Test-Path (Join-Path $stagedBackend "app\main.py"))) {
      Remove-Item -Recurse -Force $stageSrc -ErrorAction SilentlyContinue
      throw "Update refused: staged backend layout invalid"
    }
    Write-Log ("Update staged backend OK: {0}" -f $stagedBackend)

    # Only now stop a re-validated owned listener (never foreign).
    $owners = @(Get-Hf3PortListenerOwnerPids $Port)
    if ($owners.Count -gt 0) {
      $meta = Read-Hf3LaunchMeta $launchMetaFile
      $stoppedOwn = $false
      if ((Test-Hf3LaunchMetaSchema $meta) -and $owners.Count -eq 1) {
        $livePid = [int]$owners[0]
        if (([int]$meta.listener_pid -eq $livePid) -and (Test-LiveMatchesLaunchMeta -Meta $meta -LivePid $livePid)) {
          Write-Log ("Update: stopping verified launch tree listener_pid={0} before source swap" -f $livePid)
          $treeOk = Stop-VerifiedHf3LaunchTree -Meta $meta
          Start-Sleep -Seconds 1
          $still = @(Get-Hf3PortListenerOwnerPids $Port)
          if ($treeOk -and $still.Count -eq 0) {
            Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
            Remove-Item $launchMetaFile -Force -ErrorAction SilentlyContinue
            $stoppedOwn = $true
          } else {
            Write-Log "Update: owned stop incomplete — preserving launch meta; refusing source swap"
          }
        }
      }
      if (-not $stoppedOwn) {
        Remove-Item -Recurse -Force $stageSrc -ErrorAction SilentlyContinue
        throw ("EXIT_FOREIGN_LISTENER: Port 18878 in use by process(es): {0}. Stop the candidate first; refusing Update (DataDir untouched)." -f ($owners -join ','))
      }
    } else {
      # Port free: still refuse Update if a prior launcher from meta is live/unverifiable.
      $metaFree = Read-Hf3LaunchMeta $launchMetaFile
      if ($metaFree -and [int]$metaFree.launcher_pid -gt 0) {
        $liveLaunch = Get-Win32ProcessById ([int]$metaFree.launcher_pid)
        if ($liveLaunch) {
          if (-not [string]$metaFree.launcher_creation) {
            Remove-Item -Recurse -Force $stageSrc -ErrorAction SilentlyContinue
            throw "EXIT_STOP_INCOMPLETE: port free but prior launcher still live without creation proof — refuse Update"
          }
          $createMatch = $false
          $liveCreate = ""
          try { $liveCreate = ([datetime]$liveLaunch.CreationDate).ToUniversalTime().ToString("o") } catch { $liveCreate = [string]$liveLaunch.CreationDate }
          if ($liveCreate -eq [string]$metaFree.launcher_creation) {
            Write-Log ("Update: stopping verified prior launcher pid={0} before source swap" -f [int]$metaFree.launcher_pid)
            $okL = Stop-VerifiedHf3Identity -TargetPid ([int]$metaFree.launcher_pid) `
              -ExpectedCreation ([string]$metaFree.launcher_creation) `
              -Backend ([string]$metaFree.backend) -PortNum ([int]$metaFree.port) `
              -Role "launcher" -ExpectedExePath ([string]$metaFree.venv_python)
            if (-not $okL -or (Get-Win32ProcessById ([int]$metaFree.launcher_pid))) {
              Remove-Item -Recurse -Force $stageSrc -ErrorAction SilentlyContinue
              throw "EXIT_STOP_INCOMPLETE: prior launcher did not exit — refuse Update"
            }
            $createMatch = $true
          }
          if (-not $createMatch) {
            Remove-Item -Recurse -Force $stageSrc -ErrorAction SilentlyContinue
            throw "EXIT_FOREIGN_LISTENER: port free but launcher PID reused/mismatched — refuse Update"
          }
        }
      }
    }

    $backupLeaf = "src-backup-" + (Get-Date -Format "yyyyMMdd-HHmmss")
    $backup = Join-Path $CandidateRoot $backupLeaf
    $srcLeaf = Split-Path -Path $srcDir -Leaf
    $promoted = $false
    try {
      if (Test-Path $srcDir) {
        # Same-parent leaf rename — NewName must NOT be an absolute path (PS 5.1).
        Rename-Item -LiteralPath $srcDir -NewName $backupLeaf
      }
      Rename-Item -LiteralPath $stageSrc -NewName $srcLeaf
      $promoted = $true

      $backend = Find-BackendDir $srcDir
      $reqWin = Join-Path $backend "requirements-windows.txt"
      if (Test-Path $reqWin) {
        Invoke-VenvPip $venvPy @("install", "-r", $reqWin)
        Write-Log "Update reinstalled requirements-windows.txt into existing venv"
      }
      Write-Log ("Update OK — src refreshed; backup={0}; DataDir untouched" -f $backup)
    } catch {
      Write-Log ("Update FAILED — attempting rollback: {0}" -f $_.Exception.Message)
      if ($promoted) {
        if (Test-Path $srcDir) {
          $failedLeaf = "src-update-failed-" + (Get-Date -Format "yyyyMMdd-HHmmss")
          try { Rename-Item -LiteralPath $srcDir -NewName $failedLeaf } catch {
            Remove-Item -Recurse -Force $srcDir -ErrorAction SilentlyContinue
          }
        }
        if (Test-Path $backup) {
          Rename-Item -LiteralPath $backup -NewName $srcLeaf
          Write-Log "Update rollback restored previous src from backup"
        }
      } else {
        if (Test-Path $stageSrc) {
          Remove-Item -Recurse -Force $stageSrc -ErrorAction SilentlyContinue
        }
        if ((Test-Path $backup) -and -not (Test-Path $srcDir)) {
          Rename-Item -LiteralPath $backup -NewName $srcLeaf
          Write-Log "Update rollback restored src after failed promotion"
        }
      }
      throw
    }
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

    # Require uncontested 18878, or stop only a re-validated previous candidate launch.
    $preOwners = @(Get-Hf3PortListenerOwnerPids $Port)
    if ($preOwners.Count -gt 0) {
      $prevMeta = Read-Hf3LaunchMeta $launchMetaFile
      $restarted = $false
      if ((Test-Hf3LaunchMetaSchema $prevMeta) -and $preOwners.Count -eq 1) {
        $livePid = [int]$preOwners[0]
        if (([int]$prevMeta.listener_pid -eq $livePid) -and (Test-LiveMatchesLaunchMeta -Meta $prevMeta -LivePid $livePid)) {
          Write-Log ("Port $Port owned by previous verified listener pid={0} — stopping before relaunch" -f $livePid)
          $treeOk = Stop-VerifiedHf3LaunchTree -Meta $prevMeta
          Start-Sleep -Seconds 1
          if ($treeOk -and (@(Get-Hf3PortListenerOwnerPids $Port).Count -eq 0)) {
            Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
            Remove-Item $launchMetaFile -Force -ErrorAction SilentlyContinue
            $restarted = $true
          }
        }
      }
      if (-not $restarted) {
        throw ("EXIT_FOREIGN_LISTENER: Port 18878 already in use by process(es): {0}. Refusing Start (no kill)." -f ($preOwners -join ','))
      }
    } else {
      # Stale metadata with free port — free TCP ≠ absent launcher. Never kill; fail closed.
      # Stale metadata with free port — probe launcher/listener identity before any cleanup.
      $prevFree = Read-Hf3LaunchMeta $launchMetaFile
      if ($prevFree) {
        if ([bool]$prevFree.cleanup_blocked -or [bool]$prevFree.start_failed) {
          Write-Log "EXIT_START_STALE_IDENTITY_UNVERIFIED: prior start evidence cleanup_blocked/start_failed — preserving files"
          throw "EXIT_START_STALE_IDENTITY_UNVERIFIED: inspect uvicorn.launch.json before Start"
        }
        foreach ($rolePidName in @(@{Pid=[int]$prevFree.launcher_pid; Create=[string]$prevFree.launcher_creation; Role="launcher"},
                                    @{Pid=[int]$prevFree.listener_pid; Create=[string]$prevFree.listener_creation; Role="listener"})) {
          $probePid = [int]$rolePidName.Pid
          if ($probePid -le 0) { continue }
          $liveProbe = Get-Win32ProcessById $probePid
          if (-not $liveProbe) { continue }
          if (-not [string]$rolePidName.Create) {
            Write-Log ("EXIT_START_STALE_IDENTITY_UNVERIFIED: {0} pid={1} live without creation — preserving evidence" -f $rolePidName.Role, $probePid)
            throw "EXIT_START_STALE_IDENTITY_UNVERIFIED: live process without creation proof"
          }
          $liveCreate = ""
          try { $liveCreate = ([datetime]$liveProbe.CreationDate).ToUniversalTime().ToString("o") } catch { $liveCreate = [string]$liveProbe.CreationDate }
          if ($liveCreate -eq [string]$rolePidName.Create) {
            Write-Log ("EXIT_START_STALE_LAUNCHER: prior {0} still live pid={1} — refuse Start; preserving evidence (no kill)" -f $rolePidName.Role, $probePid)
            throw "EXIT_START_STALE_LAUNCHER: stop/inspect prior launch before Start"
          }
          Write-Log ("EXIT_START_STALE_IDENTITY_UNVERIFIED: {0} pid={1} creation mismatch (possible reuse) — preserving evidence" -f $rolePidName.Role, $probePid)
          throw "EXIT_START_STALE_IDENTITY_UNVERIFIED: PID reuse suspected"
        }
        # Proven absent — archive redacted meta then clear (no kill performed).
        $archiveDir = Join-Path $CandidateRoot "logs\launch-meta-archive"
        New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
        $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        Copy-Item -LiteralPath $launchMetaFile -Destination (Join-Path $archiveDir ("uvicorn.launch.archived-{0}.json" -f $stamp)) -Force
        Remove-Item $launchMetaFile -Force -ErrorAction SilentlyContinue
        if (Test-Path $pidFile) { Remove-Item $pidFile -Force -ErrorAction SilentlyContinue }
        Write-Log "Start: prior launch identities proven absent; archived redacted meta then cleared"
      } elseif (Test-Path $pidFile) {
        # Legacy pid-only evidence: probe before discard; never silent erase if live/unverifiable.
        $rawPidTxt = (Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        $legacyPid = 0
        [void][int]::TryParse(([string]$rawPidTxt).Trim(), [ref]$legacyPid)
        if ($legacyPid -gt 0) {
          $liveLegacy = Get-Win32ProcessById $legacyPid
          if ($liveLegacy) {
            Write-Log ("EXIT_STOP_BLOCKED_LEGACY_PID: uvicorn.pid={0} still live without launch meta — preserve file; refuse Start" -f $legacyPid)
            throw "EXIT_STOP_BLOCKED_LEGACY_PID: legacy PID live/unverifiable; owner must inspect"
          }
        }
        Write-Log "Ignoring stale uvicorn.pid while port is free and PID absent (no kill)"
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
      }
    }

    $launchNonce = [guid]::NewGuid().ToString("N")
    $env:MYPC_DATA_DIR = $dataDir
    $env:DATA_DIR = $dataDir
    $env:MYPC_MODELS_DIR = $modelsDir
    $env:MYPC_HF3_LAUNCH_NONCE = $launchNonce
    Write-Log "Starting uvicorn cwd=$backend DATA_DIR=$dataDir MODELS_DIR=$modelsDir bind=127.0.0.1:$Port nonce=$launchNonce"
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
    $launcherPid = [int]$proc.Id
    Set-Content -Path $pidFile -Value $launcherPid -Encoding ASCII
    Write-Log ("launcher_pid={0} — waiting for READY + verified listener ownership" -f $launcherPid)

    $ok = $false
    $failCode = "EXIT_HEALTH_NOT_READY"
    $acceptedRel = ""
    $acceptedListener = 0
    $acceptedCreation = ""
    # Capture parent→child proof while the venv redirector is still alive; after the
    # launcher exits Windows may reparent the child, so live PPID walks can fail.
    $sessionProofPid = 0
    $sessionProofCreation = ""
    $sessionProofRel = ""
    for ($i = 0; $i -lt 40; $i++) {
      Start-Sleep -Seconds 1

      $own = Resolve-Hf3ListenerOwnership -LauncherPid $launcherPid -Backend $backend -PortNum $Port
      Write-Log ("ownership_probe rel={0} listener_pid={1} reason={2}" -f $own.Relationship, $own.ListenerPid, $own.Reason)

      if ($own.Relationship -eq "AMBIGUOUS") {
        $failCode = "EXIT_AMBIGUOUS_LISTENERS"
        break
      }
      if ($own.Relationship -in @("DIRECT", "VERIFIED_DESCENDANT") -and $own.ListenerPid -gt 0) {
        $sessionProofPid = [int]$own.ListenerPid
        $sessionProofCreation = [string]$own.ListenerCreation
        $sessionProofRel = [string]$own.Relationship
      }

      $body = ""
      $statusCode = 0
      try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/v1/health" -UseBasicParsing -TimeoutSec 2
        $statusCode = [int]$r.StatusCode
        $body = [string]$r.Content
      } catch [System.Net.WebException], [System.IO.IOException], [System.TimeoutException] {
        # Transient connect errors while server boots — do not swallow ownership failures.
        continue
      } catch {
        Write-Log ("health_transport_error class={0}" -f $_.Exception.GetType().FullName)
        continue
      }

      if (-not (Test-Hf3HealthStartPass -StatusCode $statusCode -Body $body)) {
        if ($statusCode -eq 200) {
          Write-Log "HEALTH 200 but payload not status=ok + startup_phase=READY (FAIL/degraded rejected)"
          $failCode = "EXIT_HEALTH_NOT_READY"
        }
        continue
      }

      # Re-check ownership AFTER successful health payload (race-safe).
      $own2 = Resolve-Hf3ListenerOwnership -LauncherPid $launcherPid -Backend $backend -PortNum $Port
      $relOk = $false
      if ($own2.Relationship -in @("DIRECT", "VERIFIED_DESCENDANT") -and $own2.ListenerPid -gt 0) {
        $relOk = $true
        $acceptedRel = [string]$own2.Relationship
        $acceptedListener = [int]$own2.ListenerPid
        $acceptedCreation = [string]$own2.ListenerCreation
      } elseif (
        $sessionProofPid -gt 0 -and
        $own2.Relationship -ne "AMBIGUOUS"
      ) {
        # Launcher may have exited; accept sole listener only if it matches session proof.
        $ownersNow = @(Get-Hf3PortListenerOwnerPids $Port)
        if ($ownersNow.Count -eq 1 -and [int]$ownersNow[0] -eq $sessionProofPid) {
          $live = Get-Win32ProcessById $sessionProofPid
          if ($live -and -not (Test-IsConhostName $live.Name) -and
              (Test-Hf3UvicornCommandLine -CommandLine ([string]$live.CommandLine) -Backend $backend -PortNum $Port)) {
            $liveCreate = ""
            try { $liveCreate = ([datetime]$live.CreationDate).ToUniversalTime().ToString("o") } catch { $liveCreate = [string]$live.CreationDate }
            if ($sessionProofCreation -and $liveCreate -eq $sessionProofCreation) {
              $relOk = $true
              $acceptedRel = if ($sessionProofRel) { $sessionProofRel } else { "VERIFIED_DESCENDANT" }
              $acceptedListener = $sessionProofPid
              $acceptedCreation = $sessionProofCreation
              Write-Log ("ownership_session_proof_ok listener_pid={0} (launcher may have exited)" -f $sessionProofPid)
            }
          }
        }
      }
      if (-not $relOk) {
        Write-Log ("EXIT_LISTENER_OWNERSHIP: HEALTH READY but ownership rel={0} reason={1}" -f $own2.Relationship, $own2.Reason)
        $failCode = "EXIT_LISTENER_OWNERSHIP"
        break
      }
      Write-Log ("HEALTH READY ownership={0} launcher_pid={1} listener_pid={2}" -f $acceptedRel, $launcherPid, $acceptedListener)
      $ok = $true
      break
    }

    if (-not $ok) {
      Write-Log ("Start FAILED code={0} — see {1}" -f $failCode, $errLog)
      # Cleanup: only stop proven members of THIS launch with per-PID creation stamps.
      $launcherLive = Get-Win32ProcessById $launcherPid
      $launcherCreationFail = ""
      if ($launcherLive) {
        try { $launcherCreationFail = ([datetime]$launcherLive.CreationDate).ToUniversalTime().ToString("o") } catch { $launcherCreationFail = [string]$launcherLive.CreationDate }
      }
      $ownFail = Resolve-Hf3ListenerOwnership -LauncherPid $launcherPid -Backend $backend -PortNum $Port
      $listenerKillPid = 0
      $listenerKillCreation = ""
      $cleanupBlocked = $false
      if ($ownFail.Relationship -eq "AMBIGUOUS") {
        $cleanupBlocked = $true
        Write-Log "BLOCKED cleanup: EXIT_AMBIGUOUS_LISTENERS — preserving redacted start-attempt evidence"
      } elseif ($ownFail.Relationship -in @("DIRECT", "VERIFIED_DESCENDANT") -and $ownFail.ListenerPid -gt 0 -and [string]$ownFail.ListenerCreation) {
        $listenerKillPid = [int]$ownFail.ListenerPid
        $listenerKillCreation = [string]$ownFail.ListenerCreation
      } elseif ($sessionProofPid -gt 0 -and $sessionProofCreation -and $ownFail.Relationship -ne "AMBIGUOUS") {
        $listenerKillPid = $sessionProofPid
        $listenerKillCreation = $sessionProofCreation
      }
      $listenerStopOk = $true
      if (-not $cleanupBlocked) {
        if ($listenerKillPid -gt 0 -and $listenerKillCreation) {
          $listenerStopOk = Stop-VerifiedHf3Identity -TargetPid $listenerKillPid -ExpectedCreation $listenerKillCreation `
            -Backend $backend -PortNum $Port -Role "listener"
          if (-not $listenerStopOk) { $cleanupBlocked = $true }
        } else {
          $foreignOwners = @(Get-Hf3PortListenerOwnerPids $Port)
          if ($foreignOwners.Count -gt 0) {
            $cleanupBlocked = $true
            Write-Log ("BLOCKED cleanup: EXIT_FOREIGN_LISTENER / unverified owners={0} — not killing; preserving evidence" -f ($foreignOwners -join ','))
          }
        }
      }
      $launcherStopOk = $true
      if (-not $cleanupBlocked -and $launcherPid -gt 0 -and $launcherCreationFail -and $launcherPid -ne $listenerKillPid) {
        $launcherStopOk = Stop-VerifiedHf3Identity -TargetPid $launcherPid -ExpectedCreation $launcherCreationFail `
          -Backend $backend -PortNum $Port -Role "launcher" -ExpectedExePath $venvPy
        if (-not $launcherStopOk) { $cleanupBlocked = $true }
      }
      # Persist redacted attempt evidence when cleanup incomplete / foreign / ambiguous.
      $attemptMeta = @{
        schema = "mypc.hf3.launch.v1"
        port = $Port
        host = "127.0.0.1"
        backend = $backend
        venv_python = $venvPy
        launcher_pid = $launcherPid
        launcher_creation = $launcherCreationFail
        listener_pid = $(if ($listenerKillPid -gt 0) { $listenerKillPid } else { 0 })
        listener_creation = $listenerKillCreation
        relationship = [string]$ownFail.Relationship
        nonce = $launchNonce
        started_utc = (Get-Date).ToUniversalTime().ToString("o")
        start_failed = $true
        fail_code = $failCode
        cleanup_blocked = $cleanupBlocked
      }
      if ($cleanupBlocked) {
        Save-Hf3LaunchMeta -Path $launchMetaFile -Meta $attemptMeta
        if ($listenerKillPid -gt 0) {
          Set-Content -Path $pidFile -Value $listenerKillPid -Encoding ASCII
        } else {
          Set-Content -Path $pidFile -Value $launcherPid -Encoding ASCII
        }
        Write-Log "EXIT_STOP_INCOMPLETE / ownership blocked — launch meta preserved for investigation; Start remains FAILED"
      } else {
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        Remove-Item $launchMetaFile -Force -ErrorAction SilentlyContinue
      }
      throw ("{0}: Backend Start failed on 127.0.0.1:{1}" -f $failCode, $Port)
    }

    if (-not $acceptedCreation) {
      throw "EXIT_LISTENER_OWNERSHIP: Start refused — listener creation timestamp unavailable"
    }
    $launcherLiveOk = Get-Win32ProcessById $launcherPid
    $launcherCreationOk = ""
    if ($launcherLiveOk) {
      try { $launcherCreationOk = ([datetime]$launcherLiveOk.CreationDate).ToUniversalTime().ToString("o") } catch { $launcherCreationOk = [string]$launcherLiveOk.CreationDate }
    }
    # Persist durable launch identity. PID file alone is insufficient.
    $meta = @{
      schema = "mypc.hf3.launch.v1"
      port = $Port
      host = "127.0.0.1"
      backend = $backend
      venv_python = $venvPy
      launcher_pid = $launcherPid
      launcher_creation = $launcherCreationOk
      listener_pid = $acceptedListener
      listener_creation = $acceptedCreation
      relationship = $acceptedRel
      nonce = $launchNonce
      started_utc = (Get-Date).ToUniversalTime().ToString("o")
    }
    if (-not $launcherCreationOk -and $launcherPid -ne $acceptedListener) {
      Write-Log "WARN: launcher exited before meta persist — launcher_creation blank; Stop will not kill launcher PID by guess"
    }
    Save-Hf3LaunchMeta -Path $launchMetaFile -Meta $meta
    Set-Content -Path $pidFile -Value $acceptedListener -Encoding ASCII
    Write-Log ("Start OK — http://127.0.0.1:{0} listener_pid={1} rel={2} launcher_creation_present={3}" -f $Port, $acceptedListener, $acceptedRel, [bool]$launcherCreationOk)
  }
  "Stop" {
    $meta = Read-Hf3LaunchMeta $launchMetaFile
    $listeners = @(Get-Hf3PortListenerOwnerPids $Port)

    if (-not $meta) {
      if (Test-Path $pidFile) {
        Write-Log "EXIT_STOP_BLOCKED_LEGACY_PID: uvicorn.pid present without uvicorn.launch.json — refuse kill; preserving evidence"
        throw "EXIT_STOP_BLOCKED_LEGACY_PID: launch meta required; will not terminate by numeric PID alone"
      }
      Write-Log "No launch meta / pid file — nothing to stop"
      return
    }

    if (-not (Test-Hf3LaunchMetaSchema $meta)) {
      Write-Log "EXIT_STOP_BLOCKED: launch meta incomplete (schema/port/backend/listener_creation) — preserving files"
      throw "EXIT_STOP_BLOCKED: incomplete launch meta"
    }

    if ($listeners.Count -gt 1) {
      Write-Log ("EXIT_AMBIGUOUS_LISTENERS: refusing kill; preserving launch meta. owners={0}" -f ($listeners -join ','))
      throw "EXIT_AMBIGUOUS_LISTENERS: Stop refused"
    }

    if ($listeners.Count -eq 1) {
      $livePid = [int]$listeners[0]
      if (-not (([int]$meta.listener_pid -eq $livePid) -and (Test-LiveMatchesLaunchMeta -Meta $meta -LivePid $livePid))) {
        Write-Log ("EXIT_FOREIGN_LISTENER: port listener pid={0} does not match launch meta — refuse kill; preserving evidence" -f $livePid)
        throw "EXIT_FOREIGN_LISTENER: Stop refused"
      }
      Write-Log ("Stop: verified listener_pid={0} rel={1} creation_match=true launcher_creation_present={2}" -f $livePid, $meta.relationship, [bool][string]$meta.launcher_creation)
      $treeOk = Stop-VerifiedHf3LaunchTree -Meta $meta
      $left = @(Get-Hf3PortListenerOwnerPids $Port)
      if (-not $treeOk -or $left.Count -gt 0) {
        Write-Log ("EXIT_STOP_INCOMPLETE: treeOk={0} remaining_owners={1} — preserving launch meta" -f $treeOk, ($left -join ','))
        throw "EXIT_STOP_INCOMPLETE: owned listener may still be present"
      }
      Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
      Remove-Item $launchMetaFile -Force -ErrorAction SilentlyContinue
      Write-Log "Stop OK — port 18878 has no listener"
      return
    }

    # No listener: launcher cleanup is tri-state — absent / stopped / incomplete.
    Write-Log "Stop: no listener on 18878; verifying launcher identity before meta cleanup"
    $launcherPidStop = [int]$meta.launcher_pid
    if ($launcherPidStop -gt 0) {
      $liveLauncher = Get-Win32ProcessById $launcherPidStop
      if ($liveLauncher) {
        if (-not [string]$meta.launcher_creation) {
          Write-Log ("EXIT_STOP_INCOMPLETE: launcher pid={0} still live without launcher_creation — preserving meta" -f $launcherPidStop)
          throw "EXIT_STOP_INCOMPLETE: live launcher unverifiable"
        }
        $launcherOk = Stop-VerifiedHf3Identity -TargetPid $launcherPidStop `
          -ExpectedCreation ([string]$meta.launcher_creation) `
          -Backend ([string]$meta.backend) -PortNum ([int]$meta.port) `
          -Role "launcher" -ExpectedExePath ([string]$meta.venv_python)
        if (-not $launcherOk) {
          Write-Log ("EXIT_STOP_INCOMPLETE: launcher stop refused/failed pid={0} — preserving meta" -f $launcherPidStop)
          throw "EXIT_STOP_INCOMPLETE: launcher still present or unverifiable"
        }
        Start-Sleep -Milliseconds 200
        if (Get-Win32ProcessById $launcherPidStop) {
          Write-Log ("EXIT_STOP_INCOMPLETE: launcher pid={0} still alive after stop — preserving meta" -f $launcherPidStop)
          throw "EXIT_STOP_INCOMPLETE: launcher did not exit"
        }
        Write-Log ("Stop: launcher pid={0} verified stopped" -f $launcherPidStop)
      } else {
        Write-Log ("Stop: launcher pid={0} already absent" -f $launcherPidStop)
      }
    }
    $left2 = @(Get-Hf3PortListenerOwnerPids $Port)
    if ($left2.Count -eq 0) {
      Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
      Remove-Item $launchMetaFile -Force -ErrorAction SilentlyContinue
      Write-Log "Stop OK — port 18878 has no listener; launcher absent or verified stopped"
    } else {
      Write-Log ("EXIT_STOP_INCOMPLETE: remaining owners={0} — preserving launch meta" -f ($left2 -join ','))
      throw "EXIT_STOP_INCOMPLETE"
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
