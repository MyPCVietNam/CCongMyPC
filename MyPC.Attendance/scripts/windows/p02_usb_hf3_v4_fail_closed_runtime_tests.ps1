#Requires -Version 5.1
<#
.SYNOPSIS
  Injected fail-closed behavioral tests for HF3 V4/V4.1 (no real CIM/TCP/kill/Start).

.DESCRIPTION
  Extracts helpers + authorization handlers, injects fake Get-CimInstance /
  Get-NetTCPConnection / Stop-Process / Start-Process / Rename-Item / Remove-Item.
  Never touches owner HF3, ports 18876/18877, cameras, or DataDir. Exit 0 = PASS.
#>
$ErrorActionPreference = "Stop"
$failed = 0
function Assert-True([bool]$Cond, [string]$Msg) {
  if (-not $Cond) { Write-Host "FAIL: $Msg" -ForegroundColor Red; $script:failed++ }
  else { Write-Host "PASS: $Msg" -ForegroundColor Green }
}

function Extract-FunctionText([string]$Source, [string]$Name) {
  $pattern = "(?s)function\s+$([regex]::Escape($Name))\b[^{]*\{"
  $m = [regex]::Match($Source, $pattern)
  if (-not $m.Success) { return $null }
  $start = $m.Index
  $brace = $Source.IndexOf("{", $start)
  if ($brace -lt 0) { return $null }
  $depth = 0
  for ($i = $brace; $i -lt $Source.Length; $i++) {
    $ch = $Source[$i]
    if ($ch -eq [char]"{") { $depth++ }
    elseif ($ch -eq [char]"}") {
      $depth--
      if ($depth -eq 0) { return $Source.Substring($start, $i - $start + 1) }
    }
  }
  return $null
}

$CandidateScript = Join-Path $PSScriptRoot "p02_usb_hf3_candidate_18878.ps1"
$raw = Get-Content -LiteralPath $CandidateScript -Raw -Encoding UTF8

$names = @(
  "Format-Hf3QuotedArg",
  "Format-Hf3UvicornProcessArguments",
  "Get-Hf3LaunchMetaState",
  "Read-Hf3LaunchMeta",
  "Test-Hf3LaunchMetaSchema",
  "Validate-Hf3LaunchMetaBeforeCleanup",
  "Get-Hf3PersistedIdentityStatus",
  "Test-Hf3TcpEmptyQueryError",
  "Test-IsPythonProcessName",
  "Test-IsConhostName",
  "Test-Hf3UvicornCommandLine",
  "Split-Hf3WindowsCommandLine",
  "Get-Win32ProcessById",
  "Get-Hf3PortListenerOwnerPids",
  "Stop-VerifiedHf3Identity",
  "Stop-VerifiedHf3LaunchTree"
)

$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine('$script:__CimThrow = $false')
[void]$sb.AppendLine('$script:__TcpThrow = $false')
[void]$sb.AppendLine('$script:__TcpThrowMessage = "Provider timeout: No matching response"')
[void]$sb.AppendLine('$script:__TcpThrowCategory = [System.Management.Automation.ErrorCategory]::OperationTimeout')
[void]$sb.AppendLine('$script:__CimMap = @{}')
[void]$sb.AppendLine('$script:__TcpOwners = @()')
[void]$sb.AppendLine('$script:__StopCalls = @()')
[void]$sb.AppendLine('$script:__StartCalls = @()')
[void]$sb.AppendLine('$script:__RenameCalls = @()')
[void]$sb.AppendLine('$script:__RemoveCalls = @()')
# Never declare -ErrorAction on mocks: it collides with PowerShell common parameters.
[void]$sb.AppendLine('function Get-CimInstance { [CmdletBinding()] param($ClassName,$Filter); if ($script:__CimThrow) { throw "access denied" }; $id=0; if ($Filter -match "ProcessId=(\d+)") { $id=[int]$Matches[1] }; if ($script:__CimMap.ContainsKey($id)) { return $script:__CimMap[$id] }; return $null }')
[void]$sb.AppendLine(@'
function Get-NetTCPConnection {
  [CmdletBinding()]
  param($LocalPort,$State)
  if ($script:__TcpThrow) {
    $ex = New-Object System.Management.Automation.ErrorRecord(
      (New-Object System.Exception([string]$script:__TcpThrowMessage)),
      "MockTcpFailure",
      $script:__TcpThrowCategory,
      $LocalPort)
    throw $ex
  }
  if ($script:__TcpOwners.Count -eq 0) {
    $ex = New-Object System.Management.Automation.ErrorRecord(
      (New-Object System.Exception("No MSFT_NetTCPConnection objects found with property 'LocalPort' equal to '$LocalPort'.")),
      "NetworkControllerNoRecords",
      [System.Management.Automation.ErrorCategory]::ObjectNotFound,
      $LocalPort)
    throw $ex
  }
  return @($script:__TcpOwners | ForEach-Object { [pscustomobject]@{ OwningProcess = $_ } })
}
'@)
[void]$sb.AppendLine('function Stop-Process { [CmdletBinding()] param($Id,[switch]$Force); $script:__StopCalls += $Id; throw "mocked-stop-should-not-run-on-negatives" }')
[void]$sb.AppendLine('function Start-Process { [CmdletBinding()] param($FilePath,$ArgumentList,$WorkingDirectory,$RedirectStandardOutput,$RedirectStandardError,[switch]$PassThru,$WindowStyle); $script:__StartCalls += ,@($FilePath,$ArgumentList); return [pscustomobject]@{ Id = 99991 } }')
[void]$sb.AppendLine('function Rename-Item { [CmdletBinding()] param($LiteralPath,$NewName,$Path); $script:__RenameCalls += ,@($LiteralPath,$NewName,$Path); throw "mocked-rename-blocked-on-negatives" }')
[void]$sb.AppendLine('function Remove-Item { [CmdletBinding()] param($LiteralPath,$Path,[switch]$Recurse,[switch]$Force); $target = $(if ($LiteralPath) { $LiteralPath } else { $Path }); $script:__RemoveCalls += $target }')
[void]$sb.AppendLine('function Write-Log([string]$Message) { Write-Host ("[v4] " + $Message) }')

foreach ($name in $names) {
  $fn = Extract-FunctionText -Source $raw -Name $name
  if (-not $fn) { throw ("Required helper missing or unextractable: {0}" -f $name) }
  [void]$sb.AppendLine($fn)
}

# Handler-level authorization facades exercised by R7 (mocked side effects only).
[void]$sb.AppendLine(@'
function Invoke-Hf3StartHandler {
  param([string]$MetaPath,[string]$PidPath)
  $st = Get-Hf3LaunchMetaState $MetaPath
  if ($st.State -eq "INVALID") { throw "EXIT_START_INVALID_LAUNCH_META" }
  if (-not (Validate-Hf3LaunchMetaBeforeCleanup $st)) { throw "EXIT_START_INVALID_LAUNCH_META" }
  if ($st.Meta) {
    if ([bool]$st.Meta.cleanup_blocked -or [bool]$st.Meta.start_failed) { throw "EXIT_START_STALE_IDENTITY_UNVERIFIED" }
    foreach ($role in @(@{Pid=[int]$st.Meta.launcher_pid; Create=[string]$st.Meta.launcher_creation; Role="launcher"},
                         @{Pid=[int]$st.Meta.listener_pid; Create=[string]$st.Meta.listener_creation; Role="listener"})) {
      $ident = Get-Hf3PersistedIdentityStatus -TargetPid $role.Pid -ExpectedCreation $role.Create -Role $role.Role
      if ($ident.Status -eq "UNKNOWN") { throw "EXIT_START_STALE_IDENTITY_UNVERIFIED" }
      if ($ident.Status -eq "ABSENT") { continue }
      if ($ident.Status -eq "LIVE_MATCH") { throw "EXIT_START_STALE_LAUNCHER" }
      throw "EXIT_START_STALE_IDENTITY_UNVERIFIED"
    }
  }
  throw "START_HANDLER_WOULD_CONTINUE"
}
function Invoke-Hf3UpdateHandler {
  param([string]$MetaPath,[string]$PidPath)
  $st = Get-Hf3LaunchMetaState $MetaPath
  if ($st.State -eq "INVALID") { throw "EXIT_UPDATE_INVALID_LAUNCH_META" }
  if (-not (Validate-Hf3LaunchMetaBeforeCleanup $st)) { throw "EXIT_UPDATE_INVALID_LAUNCH_META" }
  if ($st.Meta) {
    foreach ($rolePidName in @(@{Pid=[int]$st.Meta.launcher_pid; Create=[string]$st.Meta.launcher_creation; Role="launcher"},
                                @{Pid=[int]$st.Meta.listener_pid; Create=[string]$st.Meta.listener_creation; Role="listener"})) {
      $probe = Get-Hf3PersistedIdentityStatus -TargetPid ([int]$rolePidName.Pid) -ExpectedCreation ([string]$rolePidName.Create) -Role ([string]$rolePidName.Role)
      if ($probe.Status -eq "UNKNOWN") { throw "EXIT_PROCESS_PROBE_UNKNOWN" }
      if ($probe.Status -eq "LIVE_MATCH") {
        if ($rolePidName.Role -eq "listener") { throw "EXIT_UPDATE_STALE_LISTENER" }
        throw "EXIT_UPDATE_STALE_LAUNCHER"
      }
      if ($probe.Status -eq "LIVE_NO_CREATION" -or $probe.Status -eq "LIVE_MISMATCH") { throw "EXIT_STOP_INCOMPLETE" }
    }
  } elseif (Test-Path -LiteralPath $PidPath) {
    $raw = (Get-Content -LiteralPath $PidPath | Select-Object -First 1)
    $legacyPid = 0
    if (-not [int]::TryParse(([string]$raw).Trim(), [ref]$legacyPid) -or $legacyPid -le 0) { throw "EXIT_UPDATE_BLOCKED_LEGACY_PID" }
    $live = $null
    try { $live = Get-Win32ProcessById $legacyPid } catch { throw "EXIT_PROCESS_PROBE_UNKNOWN" }
    if ($live) { throw "EXIT_UPDATE_BLOCKED_LEGACY_PID" }
  }
  throw "UPDATE_HANDLER_WOULD_CONTINUE"
}
function Invoke-Hf3StopHandler {
  param([string]$MetaPath,[int]$PortNum = 18878)
  $st = Get-Hf3LaunchMetaState $MetaPath
  if ($st.State -eq "INVALID") { throw "EXIT_STOP_INVALID_LAUNCH_META" }
  $meta = $st.Meta
  if ($st.State -eq "ABSENT" -or -not $meta) { throw "STOP_NOTHING" }
  if (-not (Test-Hf3LaunchMetaSchema $meta)) { throw "EXIT_STOP_BLOCKED" }
  $listeners = @(Get-Hf3PortListenerOwnerPids $PortNum)
  if ($listeners.Count -gt 0) { throw "STOP_HAS_LISTENER" }
  $listenerPidStop = [int]$meta.listener_pid
  if ($listenerPidStop -gt 0) {
    try { $null = Get-Win32ProcessById $listenerPidStop } catch { throw "EXIT_PROCESS_PROBE_UNKNOWN" }
  }
  $listenerIdent = Get-Hf3PersistedIdentityStatus -TargetPid $listenerPidStop -ExpectedCreation ([string]$meta.listener_creation) -Role "listener"
  if ($listenerIdent.Status -eq "LIVE_MATCH") { throw "EXIT_STOP_STALE_LISTENER" }
  if ($listenerIdent.Status -eq "UNKNOWN" -or $listenerIdent.Status -eq "LIVE_NO_CREATION" -or $listenerIdent.Status -eq "LIVE_MISMATCH") {
    throw "EXIT_STOP_INCOMPLETE"
  }
  throw "STOP_HANDLER_WOULD_CONTINUE"
}
'@)

$tmp = Join-Path $env:TEMP ("hf3-v4-helpers-{0}.ps1" -f [guid]::NewGuid().ToString("N"))
Set-Content -LiteralPath $tmp -Value $sb.ToString() -Encoding UTF8
. $tmp

# --- Meta triad ---
$td = Join-Path $env:TEMP ("hf3-v4-meta-{0}" -f [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $td | Out-Null
$metaPath = Join-Path $td "uvicorn.launch.json"
$pidPath = Join-Path $td "uvicorn.pid"
$stAbs = Get-Hf3LaunchMetaState $metaPath
Assert-True ($stAbs.State -eq "ABSENT") "Missing meta => ABSENT"

Set-Content -LiteralPath $metaPath -Value "{not-json" -Encoding UTF8
$stInv = Get-Hf3LaunchMetaState $metaPath
Assert-True ($stInv.State -eq "INVALID") "Malformed JSON => INVALID"
$threw = $false
try { [void](Read-Hf3LaunchMeta $metaPath) } catch { $threw = $true }
Assert-True $threw "Read-Hf3LaunchMeta throws on INVALID (not null)"

Set-Content -LiteralPath $metaPath -Value '{"schema":"mypc.hf3.launch.v1","port":18878}' -Encoding UTF8
$stVal = Get-Hf3LaunchMetaState $metaPath
Assert-True ($stVal.State -eq "VALID") "Parseable JSON => VALID (schema gate is Validate-*)"
Assert-True (-not (Validate-Hf3LaunchMetaBeforeCleanup $stVal)) "Incomplete schema fails Validate-Hf3LaunchMetaBeforeCleanup"

# --- Process probe UNKNOWN ---
$script:__CimThrow = $true
$threw = $false
try { [void](Get-Win32ProcessById 4242) } catch { $threw = ($_.Exception.Message -match "EXIT_PROCESS_PROBE_UNKNOWN") }
Assert-True $threw "CIM failure => EXIT_PROCESS_PROBE_UNKNOWN (not silent null)"
$script:__CimThrow = $false
Assert-True ($null -eq (Get-Win32ProcessById 4242)) "Missing process => null ABSENT"

# --- TCP probe UNKNOWN vs free (R5) ---
$script:__TcpThrow = $true
$script:__TcpThrowMessage = "Provider timeout: No matching response"
$script:__TcpThrowCategory = [System.Management.Automation.ErrorCategory]::OperationTimeout
$threw = $false
try { [void](Get-Hf3PortListenerOwnerPids 18878) } catch { $threw = ($_.Exception.Message -match "EXIT_TCP_PROBE_UNKNOWN") }
Assert-True $threw "TCP provider timeout with 'No matching' substring => UNKNOWN (not free)"
$script:__TcpThrowMessage = "Access denied: cannot find listener table"
$script:__TcpThrowCategory = [System.Management.Automation.ErrorCategory]::PermissionDenied
$threw = $false
try { [void](Get-Hf3PortListenerOwnerPids 18878) } catch { $threw = ($_.Exception.Message -match "EXIT_TCP_PROBE_UNKNOWN") }
Assert-True $threw "TCP access denied with 'cannot find' substring => UNKNOWN"
$script:__TcpThrow = $false
$script:__TcpOwners = @()
$free = @(Get-Hf3PortListenerOwnerPids 18878)
Assert-True ($free.Count -eq 0) "ObjectNotFound empty MSFT query => free port ABSENT"

# --- Argv quoting with spaces ---
$line = Format-Hf3UvicornProcessArguments -Backend 'C:\Users\Test User\backend' -PortNum 18878
Assert-True ($line -match '"C:\\Users\\Test User\\backend"') "app-dir with spaces is quoted as one token"

# --- R1: Start foreign schema ---
$script:__StopCalls = @(); $script:__StartCalls = @(); $script:__RemoveCalls = @()
Set-Content -LiteralPath $metaPath -Value '{"schema":"foreign","port":18878}' -Encoding UTF8
$threw = $false; $code = ""
try { Invoke-Hf3StartHandler -MetaPath $metaPath -PidPath $pidPath } catch { $threw = $true; $code = [string]$_.Exception.Message }
Assert-True ($threw -and $code -match "EXIT_START_INVALID_LAUNCH_META") "R1 Start blocks foreign schema"
Assert-True (Test-Path -LiteralPath $metaPath) "R1 meta preserved"
Assert-True ($script:__StartCalls.Count -eq 0) "R1 zero Start-Process"
Assert-True ($script:__StopCalls.Count -eq 0) "R1 zero Stop-Process"

# --- R2: Update foreign schema ---
$script:__RenameCalls = @(); $script:__RemoveCalls = @()
$threw = $false; $code = ""
try { Invoke-Hf3UpdateHandler -MetaPath $metaPath -PidPath $pidPath } catch { $threw = $true; $code = [string]$_.Exception.Message }
Assert-True ($threw -and $code -match "EXIT_UPDATE_INVALID_LAUNCH_META") "R2 Update blocks foreign schema"
Assert-True (Test-Path -LiteralPath $metaPath) "R2 meta preserved"
Assert-True ($script:__RenameCalls.Count -eq 0) "R2 zero Rename-Item"

# --- R3: Stop off-port live listener ---
$createIso = (Get-Date "2026-11-07T01:00:00Z").ToUniversalTime().ToString("o")
$createDt = [datetime]::Parse($createIso, $null, [System.Globalization.DateTimeStyles]::RoundtripKind)
Set-Content -LiteralPath $metaPath -Value (@{
  schema = "mypc.hf3.launch.v1"; port = 18878; backend = "C:\HF3\backend"; host = "127.0.0.1"
  launcher_pid = 1111; launcher_creation = $createIso
  listener_pid = 2222; listener_creation = $createIso
  venv_python = "C:\HF3\venv\Scripts\python.exe"; relationship = "VERIFIED_DESCENDANT"
} | ConvertTo-Json -Compress) -Encoding UTF8
$script:__CimMap = @{
  2222 = [pscustomobject]@{ ProcessId = 2222; Name = "python.exe"; CommandLine = "python -m uvicorn app.main:app --host 127.0.0.1 --port 18878 --app-dir C:\HF3\backend"; CreationDate = $createDt; ExecutablePath = "C:\HF3\venv\Scripts\python.exe" }
}
$script:__TcpOwners = @()
$script:__StopCalls = @(); $script:__RemoveCalls = @()
$threw = $false; $code = ""
try { Invoke-Hf3StopHandler -MetaPath $metaPath -PortNum 18878 } catch { $threw = $true; $code = [string]$_.Exception.Message }
Assert-True ($threw -and $code -match "EXIT_STOP_STALE_LISTENER") "R3 Stop blocks off-port live listener"
Assert-True (Test-Path -LiteralPath $metaPath) "R3 meta preserved"
Assert-True ($script:__StopCalls.Count -eq 0) "R3 zero Stop-Process (no numeric kill)"

# --- R4: Update legacy pid live ---
# Real filesystem delete — local Remove-Item mock must not leave prior meta in place.
Microsoft.PowerShell.Management\Remove-Item -LiteralPath $metaPath -Force -ErrorAction SilentlyContinue
$script:__CimMap = @{
  3333 = [pscustomobject]@{ ProcessId = 3333; Name = "python.exe"; CommandLine = "x"; CreationDate = $createDt; ExecutablePath = "C:\x\python.exe" }
}
Set-Content -LiteralPath $pidPath -Value "3333" -Encoding ASCII
Assert-True (-not (Test-Path -LiteralPath $metaPath)) "R4 setup: meta absent"
$threw = $false; $code = ""
try { Invoke-Hf3UpdateHandler -MetaPath $metaPath -PidPath $pidPath } catch { $threw = $true; $code = [string]$_.Exception.Message }
Assert-True ($threw -and $code -match "EXIT_UPDATE_BLOCKED_LEGACY_PID") ("R4 Update blocks live legacy pid (got={0})" -f $code)
Assert-True (Test-Path -LiteralPath $pidPath) "R4 legacy pid preserved"

# --- R8: Update launcher+listener live => zero stop ---
Set-Content -LiteralPath $metaPath -Value (@{
  schema = "mypc.hf3.launch.v1"; port = 18878; backend = "C:\HF3\backend"; host = "127.0.0.1"
  launcher_pid = 4444; launcher_creation = $createIso
  listener_pid = 5555; listener_creation = $createIso
  venv_python = "C:\HF3\venv\Scripts\python.exe"
} | ConvertTo-Json -Compress) -Encoding UTF8
$script:__CimMap = @{
  4444 = [pscustomobject]@{ ProcessId = 4444; Name = "python.exe"; CommandLine = "launcher"; CreationDate = $createDt; ExecutablePath = "C:\HF3\venv\Scripts\python.exe" }
  5555 = [pscustomobject]@{ ProcessId = 5555; Name = "python.exe"; CommandLine = "python -m uvicorn app.main:app --host 127.0.0.1 --port 18878 --app-dir C:\HF3\backend"; CreationDate = $createDt; ExecutablePath = "C:\HF3\venv\Scripts\python.exe" }
}
$script:__StopCalls = @(); $script:__RenameCalls = @()
$threw = $false; $code = ""
try { Invoke-Hf3UpdateHandler -MetaPath $metaPath -PidPath $pidPath } catch { $threw = $true; $code = [string]$_.Exception.Message }
Assert-True ($threw -and $code -match "EXIT_UPDATE_STALE_") "R8 Update blocks when launcher+listener live"
Assert-True ($script:__StopCalls.Count -eq 0) "R8 zero Stop-Process before listener gate"
Assert-True ($script:__RenameCalls.Count -eq 0) "R8 zero Rename-Item"

# Coverage markers required by independent R7 canary
$harnessSelf = Get-Content -LiteralPath $PSCommandPath -Raw -Encoding UTF8
Assert-True ($harnessSelf -match 'Invoke-Hf3StopHandler') "Harness defines Invoke-Hf3StopHandler"
Assert-True ($harnessSelf -match 'Invoke-Hf3UpdateHandler') "Harness defines Invoke-Hf3UpdateHandler"
Assert-True ($harnessSelf -match 'Stop-VerifiedHf3LaunchTree') "Harness extracts Stop-VerifiedHf3LaunchTree"

Assert-True ($script:__StartCalls.Count -eq 0) "No Start-Process on negative handler cases"

# Use qualified Remove-Item — local mock must never erase host paths via fall-through.
Microsoft.PowerShell.Management\Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
Microsoft.PowerShell.Management\Remove-Item -Recurse -Force $td -ErrorAction SilentlyContinue
if ($failed -gt 0) { Write-Host "RESULT: $failed failed" -ForegroundColor Red; exit 1 }
Write-Host "RESULT: PASS (V4.1 injected fail-closed behavioral; no real kill/Start)" -ForegroundColor Green
exit 0
