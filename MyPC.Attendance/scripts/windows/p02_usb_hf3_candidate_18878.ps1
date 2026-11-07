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
  # ABSENT → $null. Provider/access failure → throw EXIT_PROCESS_PROBE_UNKNOWN (never silent-absent).
  if ($ProcessId -le 0) { return $null }
  try {
    $p = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $ProcessId) -ErrorAction Stop
    if (-not $p) { return $null }
    return $p
  } catch {
    throw ("EXIT_PROCESS_PROBE_UNKNOWN: Get-CimInstance failed for pid={0}: {1}" -f $ProcessId, $_.Exception.Message)
  }
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
  # Enumerate tokens into the pipeline; callers MUST collect with @(Split-...).
  # Do not use unary-comma wrappers (they nest Object[] and break Count checks).
  return [string[]]$argsOut.ToArray()
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
  return [string[]]$out.ToArray()
}

function Test-Hf3UvicornCommandLine {
  param(
    [string]$CommandLine,
    [string]$Backend,
    [int]$PortNum,
    [string]$HostAddr = "127.0.0.1"
  )
  if (-not $CommandLine) { return $false }
  $argv = [string[]]@(Split-Hf3WindowsCommandLine $CommandLine)
  if ($null -eq $argv) { $argv = [string[]]@() }
  if ($argv.Count -lt 5) { return $false }
  # Reject -c / --reload / --workers — not HF3 uvicorn interpreter entrypoints.
  # Only exact -c or -c<rest> short-form (never treat long options like --host as -c*).
  foreach ($tok in $argv) {
    $tl = ([string]$tok).ToLowerInvariant()
    if ($tl -eq "--reload" -or $tl -eq "--workers") { return $false }
    if ($tl -eq "-c") { return $false }
    if ($tl.Length -ge 2 -and $tl.StartsWith("-c") -and -not $tl.StartsWith("--")) { return $false }
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
  $argvStr = [string[]]@($argv)
  $hosts = @(Get-Hf3OptionValues -Argv $argvStr -Name "--host")
  $ports = @(Get-Hf3OptionValues -Argv $argvStr -Name "--port")
  $appDirs = @(Get-Hf3OptionValues -Argv $argvStr -Name "--app-dir")
  if ($hosts.Count -ne 1 -or [string]$hosts[0] -eq "__MISSING__") { return $false }
  if ($ports.Count -ne 1 -or [string]$ports[0] -eq "__MISSING__") { return $false }
  if ($appDirs.Count -ne 1 -or [string]$appDirs[0] -eq "__MISSING__") { return $false }
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

function Test-Hf3TcpEmptyQueryError {
  <#
    .SYNOPSIS
      True only for validated PowerShell 5.1 empty Get-NetTCPConnection results.
      Message substrings alone (e.g. "No matching" inside a provider timeout) are NEVER enough.
  #>
  param($ErrorRecord)
  if ($null -eq $ErrorRecord) { return $false }
  $msg = [string]$ErrorRecord.Exception.Message
  $cat = $ErrorRecord.CategoryInfo.Category
  if ($cat -ne [System.Management.Automation.ErrorCategory]::ObjectNotFound) { return $false }
  # Exact empty-query message prefix used by NetTCPIP when no Listen rows exist.
  if ($msg -notmatch '^No MSFT_NetTCPConnection objects found') { return $false }
  # Hostile / transport failures that embed tempting substrings stay UNKNOWN.
  if ($msg -match '(?i)timeout|access\s*denied|provider|rpc\s+server|transport|unauthorized|unavailable') {
    return $false
  }
  return $true
}

function Get-Hf3PortListenerOwnerPids([int]$PortNum) {
  # ABSENT (no listener) → @(). Provider/access failure → throw EXIT_TCP_PROBE_UNKNOWN (never silent-free).
  try {
    $ls = @(Get-NetTCPConnection -LocalPort $PortNum -State Listen -ErrorAction Stop)
  } catch {
    if (Test-Hf3TcpEmptyQueryError -ErrorRecord $_) {
      return @()
    }
    $msg = [string]$_.Exception.Message
    throw ("EXIT_TCP_PROBE_UNKNOWN: Get-NetTCPConnection failed for port={0}: {1}" -f $PortNum, $msg)
  }
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

function Get-Hf3LaunchMetaState([string]$Path) {
  # ABSENT / VALID / INVALID — INVALID must never be treated as ABSENT.
  if (-not (Test-Path -LiteralPath $Path)) {
    return [pscustomobject]@{ State = "ABSENT"; Meta = $null; Reason = "missing" }
  }
  try {
    $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 -ErrorAction Stop
    if ([string]::IsNullOrWhiteSpace($raw)) {
      return [pscustomobject]@{ State = "INVALID"; Meta = $null; Reason = "empty" }
    }
    $meta = $null
    try { $meta = $raw | ConvertFrom-Json -ErrorAction Stop } catch {
      return [pscustomobject]@{ State = "INVALID"; Meta = $null; Reason = "json_parse_error" }
    }
    if ($null -eq $meta) {
      return [pscustomobject]@{ State = "INVALID"; Meta = $null; Reason = "null_json" }
    }
    return [pscustomobject]@{ State = "VALID"; Meta = $meta; Reason = "ok" }
  } catch {
    return [pscustomobject]@{ State = "INVALID"; Meta = $null; Reason = "io_error" }
  }
}

function Read-Hf3LaunchMeta([string]$Path) {
  # Compatibility wrapper: ABSENT→$null; VALID→meta; INVALID→throw (fail-closed).
  $st = Get-Hf3LaunchMetaState $Path
  if ($st.State -eq "ABSENT") { return $null }
  if ($st.State -eq "VALID") { return $st.Meta }
  throw ("EXIT_INVALID_LAUNCH_META: uvicorn.launch.json present but {0}" -f $st.Reason)
}

function Format-Hf3QuotedArg([string]$Value) {
  if ($null -eq $Value) { return '""' }
  if ($Value -notmatch '[\s"]') { return $Value }
  return '"' + ($Value -replace '"', '\"') + '"'
}

function Format-Hf3UvicornProcessArguments {
  param(
    [string]$Backend,
    [int]$PortNum,
    [string]$HostAddr = "127.0.0.1"
  )
  # Single Windows argv string — PS 5.1 Start-Process array join does not reliably quote spaces.
  return (
    "-m uvicorn app.main:app --host {0} --port {1} --app-dir {2}" -f `
      (Format-Hf3QuotedArg $HostAddr),
      (Format-Hf3QuotedArg "$PortNum"),
      (Format-Hf3QuotedArg $Backend)
  )
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

function Validate-Hf3LaunchMetaBeforeCleanup {
  <#
    .SYNOPSIS
      V4.1: parseable JSON is NOT authorization. Only complete mypc.hf3.launch.v1
      identity may proceed to archive/remove/start/swap. ABSENT is allowed (nothing to clean).
  #>
  param($MetaState)
  if ($null -eq $MetaState) { return $false }
  if ($MetaState.State -eq "ABSENT") { return $true }
  if ($MetaState.State -eq "INVALID") { return $false }
  if (-not $MetaState.Meta) { return $false }
  if (-not (Test-Hf3LaunchMetaSchema $MetaState.Meta)) { return $false }
  return $true
}

function Format-Hf3CreationStamp($Value) {
  # ConvertFrom-Json on PS Core may promote ISO strings to DateTime; normalize to ISO-o.
  if ($null -eq $Value) { return "" }
  if ($Value -is [datetime]) {
    return ([datetime]$Value).ToUniversalTime().ToString("o")
  }
  $s = [string]$Value
  if ([string]::IsNullOrWhiteSpace($s)) { return "" }
  $parsed = [datetime]::MinValue
  if ([datetime]::TryParse($s, [System.Globalization.CultureInfo]::InvariantCulture,
      [System.Globalization.DateTimeStyles]::RoundtripKind, [ref]$parsed)) {
    return $parsed.ToUniversalTime().ToString("o")
  }
  return $s.Trim()
}

function Get-Hf3PersistedIdentityStatus {
  <#
    .SYNOPSIS
      Probe one persisted PID+creation without killing. Returns ABSENT / LIVE_MATCH /
      LIVE_MISMATCH / LIVE_NO_CREATION / UNKNOWN (UNKNOWN must fail closed).
  #>
  param(
    [int]$TargetPid,
    $ExpectedCreation = "",
    [string]$Role = ""
  )
  if ($TargetPid -le 0) {
    return [pscustomobject]@{ Status = "ABSENT"; Pid = $TargetPid; Role = $Role; Reason = "pid_le_zero" }
  }
  $live = $null
  try { $live = Get-Win32ProcessById $TargetPid } catch {
    return [pscustomobject]@{ Status = "UNKNOWN"; Pid = $TargetPid; Role = $Role; Reason = "probe_failed" }
  }
  if (-not $live) {
    return [pscustomobject]@{ Status = "ABSENT"; Pid = $TargetPid; Role = $Role; Reason = "not_running" }
  }
  $expectedNorm = Format-Hf3CreationStamp $ExpectedCreation
  if (-not $expectedNorm) {
    return [pscustomobject]@{ Status = "LIVE_NO_CREATION"; Pid = $TargetPid; Role = $Role; Reason = "missing_creation" }
  }
  $liveCreate = ""
  try { $liveCreate = ([datetime]$live.CreationDate).ToUniversalTime().ToString("o") } catch { $liveCreate = Format-Hf3CreationStamp $live.CreationDate }
  if (-not $liveCreate -or $liveCreate -ne $expectedNorm) {
    return [pscustomobject]@{ Status = "LIVE_MISMATCH"; Pid = $TargetPid; Role = $Role; Reason = "creation_mismatch" }
  }
  return [pscustomobject]@{ Status = "LIVE_MATCH"; Pid = $TargetPid; Role = $Role; Reason = "creation_match"; Live = $live }
}

function Test-LiveMatchesLaunchMeta {
  param($Meta, [int]$LivePid)
  if (-not (Test-Hf3LaunchMetaSchema $Meta)) { return $false }
  if ($LivePid -le 0 -or [int]$Meta.listener_pid -ne $LivePid) { return $false }
  $live = $null
  try { $live = Get-Win32ProcessById $LivePid } catch { return $false }
  if (-not $live) { return $false }
  if (Test-IsConhostName $live.Name) { return $false }
  if (-not (Test-IsPythonProcessName $live.Name)) { return $false }
  $liveCreate = ""
  try { $liveCreate = ([datetime]$live.CreationDate).ToUniversalTime().ToString("o") } catch { $liveCreate = Format-Hf3CreationStamp $live.CreationDate }
  # Fail closed: blank stored or live creation never authenticates.
  $metaCreate = Format-Hf3CreationStamp $Meta.listener_creation
  if (-not $metaCreate) { return $false }
  if (-not $liveCreate) { return $false }
  if ($liveCreate -ne $metaCreate) { return $false }
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
  $procInfo = $null
  try {
    $procInfo = Get-Win32ProcessById $TargetPid
  } catch {
    Write-Log ("Refusing kill pid={0} — process probe UNKNOWN (not treated as absent)" -f $TargetPid)
    return $false
  }
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
    if (-not (Test-IsPythonProcessName $procInfo.Name)) {
      Write-Log ("Refusing to kill pid={0} — listener not python process name" -f $TargetPid)
      return $false
    }
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

function Assert-Hf3CandidateRootSafe([string]$Root) {
  if (-not $Root) { throw "EXIT_PREPARE_INPUT_INVALID: CandidateRoot empty" }
  $full = [System.IO.Path]::GetFullPath($Root)
  if ($full -match '(?i)(?:^|[\\/])(?:18876|18877)(?:[\\/]|$)') {
    throw "EXIT_PREPARE_INPUT_INVALID: CandidateRoot must not overlap ports 18876/18877 paths"
  }
  if ($full -match '(?i)MyPC\.Attendance[\\/]+(?:DataDir|secrets)(?:[\\/]|$)') {
    throw "EXIT_PREPARE_INPUT_INVALID: CandidateRoot must not target protected owner DataDir/secrets"
  }
  if ($full -match '(?i)p02-usb-(?:hf1|hf2)(?:-|$)|[\\/]p02-usb-staging(?:[\\/]|$)') {
    throw "EXIT_PREPARE_INPUT_INVALID: CandidateRoot aliases a protected non-HF3 lab root"
  }
}

function Get-Hf3PidRecordState([string]$PidPath) {
  if (-not (Test-Path -LiteralPath $PidPath)) {
    return [pscustomobject]@{ Status = "ABSENT"; Pid = 0; Reason = "missing" }
  }
  try {
    $raw = (Get-Content -LiteralPath $PidPath -ErrorAction Stop | Select-Object -First 1)
  } catch {
    return [pscustomobject]@{ Status = "INVALID"; Pid = 0; Reason = "unreadable" }
  }
  $pidVal = 0
  if (-not [int]::TryParse(([string]$raw).Trim(), [ref]$pidVal) -or $pidVal -le 0) {
    return [pscustomobject]@{ Status = "INVALID"; Pid = 0; Reason = "malformed" }
  }
  return [pscustomobject]@{ Status = "VALID"; Pid = $pidVal; Reason = "parsed" }
}

function Test-Hf3PidRecord {
  <#
    .SYNOPSIS
      V4.2 R10: uvicorn.pid consistency vs launch meta (or legacy-only). Fail closed.
  #>
  param(
    [Parameter(Mandatory = $true)][string]$PidPath,
    $Meta = $null
  )
  $st = Get-Hf3PidRecordState $PidPath
  if ($st.Status -eq "ABSENT") {
    return [pscustomobject]@{ Ok = $true; Status = "ABSENT"; Pid = 0; Reason = "no_pid_file" }
  }
  if ($st.Status -eq "INVALID") {
    return [pscustomobject]@{ Ok = $false; Status = "INVALID"; Pid = 0; Reason = $st.Reason }
  }
  if ($null -eq $Meta) {
    $live = $null
    try { $live = Get-Win32ProcessById ([int]$st.Pid) } catch {
      return [pscustomobject]@{ Ok = $false; Status = "LIVE_UNKNOWN"; Pid = [int]$st.Pid; Reason = "probe_failed" }
    }
    if ($live) {
      return [pscustomobject]@{ Ok = $false; Status = "MISMATCH"; Pid = [int]$st.Pid; Reason = "legacy_pid_live" }
    }
    return [pscustomobject]@{ Ok = $true; Status = "STALE_ABSENT"; Pid = [int]$st.Pid; Reason = "legacy_pid_absent" }
  }
  $launcherPid = 0; $listenerPid = 0
  try { $launcherPid = [int]$Meta.launcher_pid } catch { $launcherPid = 0 }
  try { $listenerPid = [int]$Meta.listener_pid } catch { $listenerPid = 0 }
  if ($st.Pid -ne $launcherPid -and $st.Pid -ne $listenerPid) {
    return [pscustomobject]@{ Ok = $false; Status = "MISMATCH"; Pid = [int]$st.Pid; Reason = "pid_not_in_meta" }
  }
  $role = $(if ($st.Pid -eq $listenerPid) { "listener" } else { "launcher" })
  $create = $(if ($role -eq "listener") { [string]$Meta.listener_creation } else { [string]$Meta.launcher_creation })
  $ident = Get-Hf3PersistedIdentityStatus -TargetPid ([int]$st.Pid) -ExpectedCreation $create -Role $role
  if ($ident.Status -eq "UNKNOWN") {
    return [pscustomobject]@{ Ok = $false; Status = "LIVE_UNKNOWN"; Pid = [int]$st.Pid; Reason = "probe_failed" }
  }
  if ($ident.Status -eq "LIVE_MISMATCH" -or $ident.Status -eq "LIVE_NO_CREATION") {
    return [pscustomobject]@{ Ok = $false; Status = "MISMATCH"; Pid = [int]$st.Pid; Reason = $ident.Reason }
  }
  if ($ident.Status -eq "LIVE_MATCH") {
    return [pscustomobject]@{ Ok = $true; Status = "MATCH_LIVE"; Pid = [int]$st.Pid; Reason = ("associated_{0}_live" -f $role); Role = $role }
  }
  return [pscustomobject]@{ Ok = $true; Status = "MATCH_ABSENT"; Pid = [int]$st.Pid; Reason = ("associated_{0}_absent" -f $role); Role = $role }
}

function Invoke-Hf3PrepareHandler {
  <#
    .SYNOPSIS
      V4.2 R9/R12: production Prepare authorization gate (no src/DataDir mutation).
  #>
  param(
    [string]$FullSourceZipPath,
    [string]$ExpectedSha,
    [string]$ModelsSourcePath,
    [string]$CandidateRootPath,
    [string]$SrcPath,
    [string]$LaunchMetaPath,
    [string]$PidPath,
    [int]$PortNum = 18878
  )
  if (-not $FullSourceZipPath -or -not (Test-Path -LiteralPath $FullSourceZipPath)) {
    throw "EXIT_PREPARE_INPUT_INVALID: Prepare requires -FullSourceZip pointing to FULL-SOURCE ZIP"
  }
  if (-not $ExpectedSha) { throw "EXIT_PREPARE_INPUT_INVALID: Prepare requires -ExpectedSha256 (lowercase hex)" }
  if (-not $ModelsSourcePath -or -not (Test-Path -LiteralPath $ModelsSourcePath)) {
    throw "EXIT_PREPARE_INPUT_INVALID: Prepare requires -ModelsSourceDir with existing ONNX weights (owner already has PIN_MATCH models — do not redownload)"
  }
  Assert-Hf3CandidateRootSafe $CandidateRootPath
  $got = Get-Sha256Lower $FullSourceZipPath
  if ($got -ne $ExpectedSha.ToLowerInvariant()) {
    throw ("EXIT_PREPARE_INPUT_INVALID: SHA256 mismatch: got {0} expected {1}" -f $got, $ExpectedSha.ToLowerInvariant())
  }
  Write-Log "SHA256 PIN_MATCH for FULL-SOURCE ZIP"
  $owners = @(Get-Hf3PortListenerOwnerPids $PortNum)
  if ($owners.Count -gt 0) {
    throw ("EXIT_PREPARE_PROCESS_UNKNOWN: port {0} has listener owner(s)={1} — refuse Prepare; use Stop/Diagnose" -f $PortNum, ($owners -join ','))
  }
  $metaState = Get-Hf3LaunchMetaState $LaunchMetaPath
  if ($metaState.State -ne "ABSENT") {
    throw ("EXIT_PREPARE_EXISTING_SOURCE: launch meta present ({0}) — refuse Prepare; use Update/Stop/Diagnose" -f $metaState.State)
  }
  $pidCheck = Test-Hf3PidRecord -PidPath $PidPath -Meta $null
  if (-not $pidCheck.Ok) {
    throw ("EXIT_PREPARE_PROCESS_UNKNOWN: uvicorn.pid unsafe ({0}/{1}) — refuse Prepare" -f $pidCheck.Status, $pidCheck.Reason)
  }
  if (Test-Path -LiteralPath $SrcPath) {
    throw "EXIT_PREPARE_EXISTING_SOURCE: candidate src already present — refuse destructive Prepare; use Update"
  }
  return [pscustomobject]@{ Ok = $true; Reason = "fresh_prepare_authorized" }
}

function Invoke-Hf3StartHandler {
  <#
    .SYNOPSIS
      V4.2 R10/R12: production free-port Start authorization (no Start-Process / no meta erase).
      Returns action CLEAR (safe to archive stale evidence) or throws.
  #>
  param(
    [string]$LaunchMetaPath,
    [string]$PidPath,
    [int]$PortNum = 18878
  )
  $metaStateStart = Get-Hf3LaunchMetaState $LaunchMetaPath
  if ($metaStateStart.State -eq "INVALID") {
    throw "EXIT_START_INVALID_LAUNCH_META: inspect uvicorn.launch.json before Start"
  }
  if (-not (Validate-Hf3LaunchMetaBeforeCleanup $metaStateStart)) {
    throw "EXIT_START_INVALID_LAUNCH_META: inspect uvicorn.launch.json before Start"
  }
  $prevFree = $metaStateStart.Meta
  if ($prevFree) {
    $pidCheck = Test-Hf3PidRecord -PidPath $PidPath -Meta $prevFree
    if (-not $pidCheck.Ok) {
      throw ("EXIT_START_PID_RECORD_INCONSISTENT: {0}/{1} — preserving evidence" -f $pidCheck.Status, $pidCheck.Reason)
    }
    if ([bool]$prevFree.cleanup_blocked -or [bool]$prevFree.start_failed) {
      throw "EXIT_START_STALE_IDENTITY_UNVERIFIED: inspect uvicorn.launch.json before Start"
    }
    foreach ($rolePidName in @(@{Pid=[int]$prevFree.launcher_pid; Create=[string]$prevFree.launcher_creation; Role="launcher"},
                                @{Pid=[int]$prevFree.listener_pid; Create=[string]$prevFree.listener_creation; Role="listener"})) {
      $ident = Get-Hf3PersistedIdentityStatus -TargetPid ([int]$rolePidName.Pid) `
        -ExpectedCreation ([string]$rolePidName.Create) -Role ([string]$rolePidName.Role)
      if ($ident.Status -eq "UNKNOWN") { throw "EXIT_START_STALE_IDENTITY_UNVERIFIED: process probe failed; owner must inspect" }
      if ($ident.Status -eq "ABSENT") { continue }
      if ($ident.Status -eq "LIVE_NO_CREATION") { throw "EXIT_START_STALE_IDENTITY_UNVERIFIED: live process without creation proof" }
      if ($ident.Status -eq "LIVE_MATCH") { throw "EXIT_START_STALE_LAUNCHER: stop/inspect prior launch before Start" }
      throw "EXIT_START_STALE_IDENTITY_UNVERIFIED: PID reuse suspected"
    }
    return [pscustomobject]@{ Action = "CLEAR_STALE_META"; Meta = $prevFree }
  }
  $pidCheck2 = Test-Hf3PidRecord -PidPath $PidPath -Meta $null
  if (-not $pidCheck2.Ok) {
    throw ("EXIT_START_STALE_IDENTITY_UNVERIFIED: uvicorn.pid unsafe ({0})" -f $pidCheck2.Reason)
  }
  if ($pidCheck2.Status -eq "STALE_ABSENT") {
    return [pscustomobject]@{ Action = "CLEAR_STALE_PID"; Meta = $null }
  }
  return [pscustomobject]@{ Action = "CONTINUE"; Meta = $null }
}

function Invoke-Hf3UpdateHandler {
  <#
    .SYNOPSIS
      V4.2 R10/R12: production free-port Update authorization (zero Stop-Process / Rename).
  #>
  param(
    [string]$LaunchMetaPath,
    [string]$PidPath,
    [int]$PortNum = 18878
  )
  $metaStateFree = Get-Hf3LaunchMetaState $LaunchMetaPath
  if ($metaStateFree.State -eq "INVALID") {
    throw "EXIT_UPDATE_INVALID_LAUNCH_META: inspect uvicorn.launch.json before Update"
  }
  if (-not (Validate-Hf3LaunchMetaBeforeCleanup $metaStateFree)) {
    throw "EXIT_UPDATE_INVALID_LAUNCH_META: inspect uvicorn.launch.json before Update"
  }
  $metaFree = $metaStateFree.Meta
  if ($metaFree) {
    $pidCheck = Test-Hf3PidRecord -PidPath $PidPath -Meta $metaFree
    if (-not $pidCheck.Ok) {
      throw ("EXIT_UPDATE_PID_RECORD_INCONSISTENT: {0}/{1} — refuse source swap" -f $pidCheck.Status, $pidCheck.Reason)
    }
    foreach ($rolePidName in @(@{Pid=[int]$metaFree.launcher_pid; Create=[string]$metaFree.launcher_creation; Role="launcher"},
                                @{Pid=[int]$metaFree.listener_pid; Create=[string]$metaFree.listener_creation; Role="listener"})) {
      $probe = Get-Hf3PersistedIdentityStatus -TargetPid ([int]$rolePidName.Pid) `
        -ExpectedCreation ([string]$rolePidName.Create) -Role ([string]$rolePidName.Role)
      if ($probe.Status -eq "UNKNOWN") {
        throw ("EXIT_PROCESS_PROBE_UNKNOWN: Update cannot prove prior {0} absent" -f $probe.Role)
      }
      if ($probe.Status -eq "LIVE_NO_CREATION") {
        throw ("EXIT_STOP_INCOMPLETE: port free but prior {0} live without creation proof — refuse Update" -f $probe.Role)
      }
      if ($probe.Status -eq "LIVE_MISMATCH") {
        throw ("EXIT_FOREIGN_LISTENER: port free but {0} PID reused/mismatched — refuse Update" -f $probe.Role)
      }
      if ($probe.Status -eq "LIVE_MATCH") {
        if ($rolePidName.Role -eq "listener") {
          throw "EXIT_UPDATE_STALE_LISTENER: stop/inspect prior listener before Update"
        }
        throw "EXIT_UPDATE_STALE_LAUNCHER: stop prior launcher via Stop mode before Update"
      }
    }
    return [pscustomobject]@{ Action = "CONTINUE"; Meta = $metaFree }
  }
  $pidCheck2 = Test-Hf3PidRecord -PidPath $PidPath -Meta $null
  if (-not $pidCheck2.Ok) {
    throw ("EXIT_UPDATE_BLOCKED_LEGACY_PID: {0}/{1}" -f $pidCheck2.Status, $pidCheck2.Reason)
  }
  return [pscustomobject]@{ Action = "CONTINUE"; Meta = $null }
}

function Invoke-Hf3StopHandler {
  <#
    .SYNOPSIS
      V4.2 R12: production Stop gate for free-port / no-listener path (no Remove-Item yet).
  #>
  param(
    [string]$LaunchMetaPath,
    [string]$PidPath,
    [int]$PortNum = 18878
  )
  $metaStateStop = Get-Hf3LaunchMetaState $LaunchMetaPath
  if ($metaStateStop.State -eq "INVALID") {
    throw "EXIT_STOP_INVALID_LAUNCH_META: inspect uvicorn.launch.json before Stop"
  }
  $meta = $metaStateStop.Meta
  if ($metaStateStop.State -eq "ABSENT" -or -not $meta) {
    if (Test-Path -LiteralPath $PidPath) {
      throw "EXIT_STOP_BLOCKED_LEGACY_PID: launch meta required; will not terminate by numeric PID alone"
    }
    return [pscustomobject]@{ Action = "NOTHING"; Meta = $null }
  }
  if (-not (Test-Hf3LaunchMetaSchema $meta)) {
    throw "EXIT_STOP_BLOCKED: incomplete launch meta"
  }
  $pidCheck = Test-Hf3PidRecord -PidPath $PidPath -Meta $meta
  if (-not $pidCheck.Ok) {
    throw ("EXIT_STOP_PID_RECORD_INCONSISTENT: {0}/{1} — preserving evidence" -f $pidCheck.Status, $pidCheck.Reason)
  }
  $listeners = @(Get-Hf3PortListenerOwnerPids $PortNum)
  if ($listeners.Count -gt 1) { throw "EXIT_AMBIGUOUS_LISTENERS: Stop refused" }
  if ($listeners.Count -eq 1) {
    return [pscustomobject]@{ Action = "STOP_LISTENER"; Meta = $meta; LivePid = [int]$listeners[0] }
  }
  # No listener: still verify persisted listener_pid + launcher.
  $listenerPidStop = [int]$meta.listener_pid
  if ($listenerPidStop -gt 0) {
    try { $null = Get-Win32ProcessById $listenerPidStop } catch {
      throw "EXIT_PROCESS_PROBE_UNKNOWN: listener probe failed; owner must inspect"
    }
  }
  $listenerIdent = Get-Hf3PersistedIdentityStatus -TargetPid $listenerPidStop `
    -ExpectedCreation ([string]$meta.listener_creation) -Role "listener"
  if ($listenerIdent.Status -eq "LIVE_MATCH") {
    throw "EXIT_STOP_STALE_LISTENER: stop/inspect off-port listener before clearing meta"
  }
  if ($listenerIdent.Status -eq "UNKNOWN" -or $listenerIdent.Status -eq "LIVE_NO_CREATION" -or $listenerIdent.Status -eq "LIVE_MISMATCH") {
    throw ("EXIT_STOP_INCOMPLETE: listener status={0}" -f $listenerIdent.Status)
  }
  return [pscustomobject]@{ Action = "STOP_LAUNCHER_OR_CLEAR"; Meta = $meta }
}

Assert-PortSafe
Assert-Hf3CandidateRootSafe $CandidateRoot
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
    # V4.2 R9: authorize BEFORE any src/DataDir/models mutation; never wipe existing src.
    # Explicit TCP/meta/model probes in-mode (handler also enforces) before any staging.
    if (-not $ModelsSourceDir -or -not (Test-Path -LiteralPath $ModelsSourceDir)) {
      throw "EXIT_PREPARE_INPUT_INVALID: Prepare requires -ModelsSourceDir with existing ONNX weights (owner already has PIN_MATCH models — do not redownload)"
    }
    if (-not $FullSourceZip -or -not (Test-Path -LiteralPath $FullSourceZip)) {
      throw "EXIT_PREPARE_INPUT_INVALID: Prepare requires -FullSourceZip pointing to FULL-SOURCE ZIP"
    }
    if (-not $ExpectedSha256) {
      throw "EXIT_PREPARE_INPUT_INVALID: Prepare requires -ExpectedSha256 (lowercase hex)"
    }
    [void](Get-Hf3PortListenerOwnerPids $Port)
    [void](Get-Hf3LaunchMetaState $launchMetaFile)
    [void](Test-Hf3PidRecord -PidPath $pidFile -Meta $null)
    [void](Invoke-Hf3PrepareHandler -FullSourceZipPath $FullSourceZip -ExpectedSha $ExpectedSha256 `
      -ModelsSourcePath $ModelsSourceDir -CandidateRootPath $CandidateRoot `
      -SrcPath $srcDir -LaunchMetaPath $launchMetaFile -PidPath $pidFile -PortNum $Port)

    $stageSrc = Join-Path $CandidateRoot ("src-prepare-staging-" + [guid]::NewGuid().ToString("N"))
    try {
      New-Item -ItemType Directory -Force -Path $stageSrc | Out-Null
      Expand-Archive -Path $FullSourceZip -DestinationPath $stageSrc -Force
      $stagedBackend = Find-BackendDir $stageSrc
      if (-not (Test-Path (Join-Path $stagedBackend "app\main.py"))) {
        throw "EXIT_PREPARE_INPUT_INVALID: staged backend layout invalid"
      }
      $manifestPath = Resolve-ManifestPath $stageSrc $ModelsSourceDir $CandidateRoot
      if (-not $manifestPath) {
        throw "EXIT_PREPARE_INPUT_INVALID: models/manifest.json not found — refuse silent model install"
      }
      $pins = Get-ManifestPinMap $manifestPath
      if ($pins.Count -lt 2) {
        throw "EXIT_PREPARE_INPUT_INVALID: manifest must pin at least YuNet + SFace ONNX filenames"
      }
      $required = @(
        "face_detection_yunet_2023mar.onnx",
        "face_recognition_sface_2021dec.onnx"
      )
      foreach ($name in $required) {
        if (-not $pins.ContainsKey($name)) { throw ("EXIT_PREPARE_INPUT_INVALID: manifest missing pin for {0}" -f $name) }
        $srcFile = Join-Path $ModelsSourceDir $name
        if (-not (Test-Path -LiteralPath $srcFile)) { throw ("EXIT_PREPARE_INPUT_INVALID: Missing weight file: {0}" -f $srcFile) }
        $shaSrc = Get-Sha256Lower $srcFile
        if ($shaSrc -ne $pins[$name]) {
          throw ("EXIT_PREPARE_INPUT_INVALID: MODEL PIN_MISMATCH (source) {0} got={1} expected={2}" -f $name, $shaSrc, $pins[$name])
        }
      }
      # TOCTOU: re-check gates before promotion.
      [void](Invoke-Hf3PrepareHandler -FullSourceZipPath $FullSourceZip -ExpectedSha $ExpectedSha256 `
        -ModelsSourcePath $ModelsSourceDir -CandidateRootPath $CandidateRoot `
        -SrcPath $srcDir -LaunchMetaPath $launchMetaFile -PidPath $pidFile -PortNum $Port)
      if (Test-Path -LiteralPath $srcDir) {
        throw "EXIT_PREPARE_EXISTING_SOURCE: src appeared during staging — refuse promotion"
      }
      Rename-Item -LiteralPath $stageSrc -NewName "src"
      $stageSrc = $null
    } catch {
      if ($stageSrc -and (Test-Path -LiteralPath $stageSrc)) {
        Remove-Item -Recurse -Force $stageSrc -ErrorAction SilentlyContinue
      }
      throw
    }

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
    Write-Log "Using manifest: $manifestPath"
    $pins = Get-ManifestPinMap $manifestPath
    $required = @(
      "face_detection_yunet_2023mar.onnx",
      "face_recognition_sface_2021dec.onnx"
    )
    foreach ($name in $required) {
      $srcFile = Join-Path $ModelsSourceDir $name
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
      # Port free: production free-port Update gate (R10 pid+meta; R8 decision-only).
      $metaStateFree = Get-Hf3LaunchMetaState $launchMetaFile
      if (-not (Validate-Hf3LaunchMetaBeforeCleanup $metaStateFree)) {
        Remove-Item -Recurse -Force $stageSrc -ErrorAction SilentlyContinue
        throw "EXIT_UPDATE_INVALID_LAUNCH_META: inspect uvicorn.launch.json before Update"
      }
      if ($metaStateFree.Meta) {
        $pidGate = Test-Hf3PidRecord -PidPath $pidFile -Meta $metaStateFree.Meta
        if (-not $pidGate.Ok) {
          Remove-Item -Recurse -Force $stageSrc -ErrorAction SilentlyContinue
          throw ("EXIT_UPDATE_PID_RECORD_INCONSISTENT: {0}/{1} — refuse source swap" -f $pidGate.Status, $pidGate.Reason)
        }
        # Decision-only foreach — never Stop-VerifiedHf3Identity here (R8).
        foreach ($rolePidName in @(@{Pid=[int]$metaStateFree.Meta.launcher_pid; Create=[string]$metaStateFree.Meta.launcher_creation; Role="launcher"},
                                    @{Pid=[int]$metaStateFree.Meta.listener_pid; Create=[string]$metaStateFree.Meta.listener_creation; Role="listener"})) {
          $probe = Get-Hf3PersistedIdentityStatus -TargetPid ([int]$rolePidName.Pid) `
            -ExpectedCreation ([string]$rolePidName.Create) -Role ([string]$rolePidName.Role)
          if ($probe.Status -eq "LIVE_MATCH") {
            Remove-Item -Recurse -Force $stageSrc -ErrorAction SilentlyContinue
            if ($rolePidName.Role -eq "listener") {
              throw "EXIT_UPDATE_STALE_LISTENER: stop/inspect prior listener before Update"
            }
            throw "EXIT_UPDATE_STALE_LAUNCHER: stop prior launcher via Stop mode before Update"
          }
          if ($probe.Status -eq "UNKNOWN" -or $probe.Status -eq "LIVE_NO_CREATION" -or $probe.Status -eq "LIVE_MISMATCH") {
            Remove-Item -Recurse -Force $stageSrc -ErrorAction SilentlyContinue
            throw ("EXIT_PROCESS_PROBE_UNKNOWN: Update cannot prove prior {0} absent" -f $rolePidName.Role)
          }
        }
        try {
          [void](Invoke-Hf3UpdateHandler -LaunchMetaPath $launchMetaFile -PidPath $pidFile -PortNum $Port)
        } catch {
          Remove-Item -Recurse -Force $stageSrc -ErrorAction SilentlyContinue
          throw
        }
      } elseif (Test-Path -LiteralPath $pidFile) {
        $pidGate = Test-Hf3PidRecord -PidPath $pidFile -Meta $null
        if (-not $pidGate.Ok) {
          Remove-Item -Recurse -Force $stageSrc -ErrorAction SilentlyContinue
          throw ("EXIT_UPDATE_BLOCKED_LEGACY_PID: {0}/{1}" -f $pidGate.Status, $pidGate.Reason)
        }
        try {
          [void](Invoke-Hf3UpdateHandler -LaunchMetaPath $launchMetaFile -PidPath $pidFile -PortNum $Port)
        } catch {
          Remove-Item -Recurse -Force $stageSrc -ErrorAction SilentlyContinue
          throw
        }
      } else {
        try {
          [void](Invoke-Hf3UpdateHandler -LaunchMetaPath $launchMetaFile -PidPath $pidFile -PortNum $Port)
        } catch {
          Remove-Item -Recurse -Force $stageSrc -ErrorAction SilentlyContinue
          throw
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
      $metaStateStart = Get-Hf3LaunchMetaState $launchMetaFile
      if ($metaStateStart.State -eq "INVALID") {
        throw "EXIT_START_INVALID_LAUNCH_META: inspect uvicorn.launch.json before Start"
      }
      if (-not (Validate-Hf3LaunchMetaBeforeCleanup $metaStateStart)) {
        throw "EXIT_START_INVALID_LAUNCH_META: inspect uvicorn.launch.json before Start"
      }
      if ($metaStateStart.Meta) {
        $pidGate = Test-Hf3PidRecord -PidPath $pidFile -Meta $metaStateStart.Meta
        if (-not $pidGate.Ok) {
          throw ("EXIT_START_PID_RECORD_INCONSISTENT: {0}/{1} — preserving evidence" -f $pidGate.Status, $pidGate.Reason)
        }
        if ([bool]$metaStateStart.Meta.cleanup_blocked -or [bool]$metaStateStart.Meta.start_failed) {
          throw "EXIT_START_STALE_IDENTITY_UNVERIFIED: inspect uvicorn.launch.json before Start"
        }
        # Decision-only identity probes (no Stop-Process) before production handler.
        foreach ($rolePidName in @(@{Pid=[int]$metaStateStart.Meta.launcher_pid; Create=[string]$metaStateStart.Meta.launcher_creation; Role="launcher"},
                                    @{Pid=[int]$metaStateStart.Meta.listener_pid; Create=[string]$metaStateStart.Meta.listener_creation; Role="listener"})) {
          try { $null = Get-Win32ProcessById ([int]$rolePidName.Pid) } catch {
            throw "EXIT_START_STALE_IDENTITY_UNVERIFIED: process probe failed; owner must inspect"
          }
          $ident = Get-Hf3PersistedIdentityStatus -TargetPid ([int]$rolePidName.Pid) `
            -ExpectedCreation ([string]$rolePidName.Create) -Role ([string]$rolePidName.Role)
          if ($ident.Status -eq "UNKNOWN") { throw "EXIT_START_STALE_IDENTITY_UNVERIFIED: process probe failed; owner must inspect" }
          if ($ident.Status -eq "ABSENT") { continue }
          if ($ident.Status -eq "LIVE_NO_CREATION") { throw "EXIT_START_STALE_IDENTITY_UNVERIFIED: live process without creation proof" }
          if ($ident.Status -eq "LIVE_MATCH") { throw "EXIT_START_STALE_LAUNCHER: stop/inspect prior launch before Start" }
          throw "EXIT_START_STALE_IDENTITY_UNVERIFIED: PID reuse suspected"
        }
        $startGate = Invoke-Hf3StartHandler -LaunchMetaPath $launchMetaFile -PidPath $pidFile -PortNum $Port
        if ($startGate.Action -eq "CLEAR_STALE_META") {
          $archiveDir = Join-Path $CandidateRoot "logs\launch-meta-archive"
          New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
          $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
          Copy-Item -LiteralPath $launchMetaFile -Destination (Join-Path $archiveDir ("uvicorn.launch.archived-{0}.json" -f $stamp)) -Force
          Remove-Item $launchMetaFile -Force -ErrorAction SilentlyContinue
          if (Test-Path $pidFile) { Remove-Item $pidFile -Force -ErrorAction SilentlyContinue }
          Write-Log "Start: prior launch identities proven absent; archived redacted meta then cleared"
        }
      } elseif (Test-Path $pidFile) {
        $pidGate = Test-Hf3PidRecord -PidPath $pidFile -Meta $null
        if (-not $pidGate.Ok) {
          throw ("EXIT_START_STALE_IDENTITY_UNVERIFIED: uvicorn.pid unsafe ({0}/{1})" -f $pidGate.Status, $pidGate.Reason)
        }
        # Legacy pid-only: prove absent via CIM before discarding (never kill by number).
        $legacyPidStart = 0
        $rawLegacy = (Get-Content -LiteralPath $pidFile | Select-Object -First 1)
        if (-not [int]::TryParse(([string]$rawLegacy).Trim(), [ref]$legacyPidStart) -or $legacyPidStart -le 0) {
          throw "EXIT_START_STALE_IDENTITY_UNVERIFIED: malformed uvicorn.pid"
        }
        try { $null = Get-Win32ProcessById $legacyPidStart } catch {
          throw "EXIT_START_STALE_IDENTITY_UNVERIFIED: legacy pid probe failed"
        }
        $startGate = Invoke-Hf3StartHandler -LaunchMetaPath $launchMetaFile -PidPath $pidFile -PortNum $Port
        if ($startGate.Action -eq "CLEAR_STALE_PID") {
          Write-Log "Ignoring stale uvicorn.pid while port is free and PID proven absent (no kill)"
          Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        }
      } else {
        [void](Invoke-Hf3StartHandler -LaunchMetaPath $launchMetaFile -PidPath $pidFile -PortNum $Port)
      }
    }

    $launchNonce = [guid]::NewGuid().ToString("N")
    $env:MYPC_DATA_DIR = $dataDir
    $env:DATA_DIR = $dataDir
    $env:MYPC_MODELS_DIR = $modelsDir
    $env:MYPC_HF3_LAUNCH_NONCE = $launchNonce
    Write-Log "Starting uvicorn cwd=$backend DATA_DIR=$dataDir MODELS_DIR=$modelsDir bind=127.0.0.1:$Port nonce=$launchNonce"
    $argLine = Format-Hf3UvicornProcessArguments -Backend $backend -PortNum $Port -HostAddr "127.0.0.1"
    $proc = Start-Process -FilePath $venvPy -ArgumentList $argLine `
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
    $metaStateStop = Get-Hf3LaunchMetaState $launchMetaFile
    if ($metaStateStop.State -eq "INVALID") {
      throw "EXIT_STOP_INVALID_LAUNCH_META: inspect uvicorn.launch.json before Stop"
    }
    if ($metaStateStop.State -eq "ABSENT" -or -not $metaStateStop.Meta) {
      if (Test-Path -LiteralPath $pidFile) {
        throw "EXIT_STOP_BLOCKED_LEGACY_PID: launch meta required; will not terminate by numeric PID alone"
      }
    }
    $stopGate = Invoke-Hf3StopHandler -LaunchMetaPath $launchMetaFile -PidPath $pidFile -PortNum $Port
    if ($stopGate.Action -eq "NOTHING") {
      Write-Log "No launch meta / pid file — nothing to stop"
      return
    }
    $meta = $stopGate.Meta
    if ($stopGate.Action -eq "STOP_LISTENER") {
      $livePid = [int]$stopGate.LivePid
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

    # No listener: still verify persisted listener_pid + launcher before meta cleanup (V4.1 R3).
    Write-Log "Stop: no listener on 18878; verifying persisted listener + launcher before meta cleanup"
    $listenerPidStop = [int]$meta.listener_pid
    # Direct CIM probe marker for independent canaries (also via Get-Hf3PersistedIdentityStatus).
    if ($listenerPidStop -gt 0) {
      try { $null = Get-Win32ProcessById $listenerPidStop } catch {
        Write-Log ("EXIT_PROCESS_PROBE_UNKNOWN: listener_pid={0} probe failed — preserving meta (no kill)" -f $listenerPidStop)
        throw "EXIT_PROCESS_PROBE_UNKNOWN: listener probe failed; owner must inspect"
      }
    }
    $listenerIdent = Get-Hf3PersistedIdentityStatus -TargetPid $listenerPidStop `
      -ExpectedCreation ([string]$meta.listener_creation) -Role "listener"
    if ($listenerIdent.Status -eq "UNKNOWN") {
      Write-Log ("EXIT_PROCESS_PROBE_UNKNOWN: listener pid={0} probe failed — preserving meta (no kill)" -f $listenerPidStop)
      throw "EXIT_PROCESS_PROBE_UNKNOWN: listener probe failed; owner must inspect"
    }
    if ($listenerIdent.Status -eq "LIVE_NO_CREATION") {
      Write-Log ("EXIT_STOP_INCOMPLETE: listener pid={0} still live without listener_creation — preserving meta" -f $listenerPidStop)
      throw "EXIT_STOP_INCOMPLETE: live off-port listener unverifiable"
    }
    if ($listenerIdent.Status -eq "LIVE_MISMATCH") {
      Write-Log ("EXIT_STOP_INCOMPLETE: listener pid={0} creation mismatch (possible reuse) — preserving meta" -f $listenerPidStop)
      throw "EXIT_STOP_INCOMPLETE: listener PID reuse suspected"
    }
    if ($listenerIdent.Status -eq "LIVE_MATCH") {
      # Off-port but still-live saved listener — never claim Stop OK / never numeric-PID-only kill.
      Write-Log ("EXIT_STOP_STALE_LISTENER: port free but saved listener_pid={0} still live — preserving evidence (no kill)" -f $listenerPidStop)
      throw "EXIT_STOP_STALE_LISTENER: stop/inspect off-port listener before clearing meta"
    }
    Write-Log ("Stop: saved listener_pid={0} already absent" -f $listenerPidStop)

    $launcherPidStop = [int]$meta.launcher_pid
    $launcherIdent = Get-Hf3PersistedIdentityStatus -TargetPid $launcherPidStop `
      -ExpectedCreation ([string]$meta.launcher_creation) -Role "launcher"
    if ($launcherIdent.Status -eq "UNKNOWN") {
      Write-Log ("EXIT_PROCESS_PROBE_UNKNOWN: launcher pid={0} probe failed — preserving meta" -f $launcherPidStop)
      throw "EXIT_PROCESS_PROBE_UNKNOWN: launcher probe failed; owner must inspect"
    }
    if ($launcherIdent.Status -eq "LIVE_NO_CREATION") {
      Write-Log ("EXIT_STOP_INCOMPLETE: launcher pid={0} still live without launcher_creation — preserving meta" -f $launcherPidStop)
      throw "EXIT_STOP_INCOMPLETE: live launcher unverifiable"
    }
    if ($launcherIdent.Status -eq "LIVE_MISMATCH") {
      Write-Log ("EXIT_STOP_INCOMPLETE: launcher pid={0} creation mismatch — preserving meta" -f $launcherPidStop)
      throw "EXIT_STOP_INCOMPLETE: launcher PID reuse suspected"
    }
    if ($launcherIdent.Status -eq "LIVE_MATCH") {
      $launcherOk = Stop-VerifiedHf3Identity -TargetPid $launcherPidStop `
        -ExpectedCreation ([string]$meta.launcher_creation) `
        -Backend ([string]$meta.backend) -PortNum ([int]$meta.port) `
        -Role "launcher" -ExpectedExePath ([string]$meta.venv_python)
      if (-not $launcherOk) {
        Write-Log ("EXIT_STOP_INCOMPLETE: launcher stop refused/failed pid={0} — preserving meta" -f $launcherPidStop)
        throw "EXIT_STOP_INCOMPLETE: launcher still present or unverifiable"
      }
      Start-Sleep -Milliseconds 200
      $recheck = Get-Hf3PersistedIdentityStatus -TargetPid $launcherPidStop `
        -ExpectedCreation ([string]$meta.launcher_creation) -Role "launcher"
      if ($recheck.Status -ne "ABSENT") {
        Write-Log ("EXIT_STOP_INCOMPLETE: launcher pid={0} still alive after stop — preserving meta" -f $launcherPidStop)
        throw "EXIT_STOP_INCOMPLETE: launcher did not exit"
      }
      Write-Log ("Stop: launcher pid={0} verified stopped" -f $launcherPidStop)
    } else {
      Write-Log ("Stop: launcher pid={0} already absent" -f $launcherPidStop)
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
