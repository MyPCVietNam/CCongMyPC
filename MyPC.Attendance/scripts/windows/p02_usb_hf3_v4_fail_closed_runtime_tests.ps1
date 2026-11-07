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

function Extract-ModeText([string]$Source, [string]$ModeName, [string]$NextMode) {
  # V4.2 R12: extract production switch-mode bodies (not duplicated facades).
  $pattern = '(?s)"' + [regex]::Escape($ModeName) + '"\s*\{'
  $m = [regex]::Match($Source, $pattern)
  if (-not $m.Success) { return $null }
  $start = $m.Index + $m.Length
  $next = $Source.IndexOf('"' + $NextMode + '" {', $start)
  if ($next -lt 0) { $next = $Source.Length }
  return $Source.Substring($start, $next - $start)
}

$CandidateScript = Join-Path $PSScriptRoot "p02_usb_hf3_candidate_18878.ps1"
$raw = Get-Content -LiteralPath $CandidateScript -Raw -Encoding UTF8
$script:__PrepareModeBody = Extract-ModeText -Source $raw -ModeName "Prepare" -NextMode "Update"
Assert-True ($null -ne $script:__PrepareModeBody -and $script:__PrepareModeBody.Length -gt 20) "Extract-ModeText Prepare production body"

$names = @(
  "Format-Hf3QuotedArg",
  "Format-Hf3UvicornProcessArguments",
  "Get-Hf3LaunchMetaState",
  "Read-Hf3LaunchMeta",
  "Test-Hf3LaunchMetaSchema",
  "Validate-Hf3LaunchMetaBeforeCleanup",
  "Format-Hf3CreationStamp",
  "Get-Hf3PersistedIdentityStatus",
  "Get-Hf3PidRecordState",
  "Test-Hf3PidRecord",
  "Assert-Hf3CandidateRootSafe",
  "Test-Hf3TcpEmptyQueryError",
  "Test-IsPythonProcessName",
  "Test-IsConhostName",
  "Test-Hf3UvicornCommandLine",
  "Split-Hf3WindowsCommandLine",
  "Get-Win32ProcessById",
  "Get-Hf3PortListenerOwnerPids",
  "Stop-VerifiedHf3Identity",
  "Stop-VerifiedHf3LaunchTree",
  "Get-Sha256Lower",
  "Invoke-Hf3PrepareHandler",
  "Invoke-Hf3StartHandler",
  "Invoke-Hf3UpdateHandler",
  "Invoke-Hf3StopHandler"
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
[void]$sb.AppendLine('$script:__ShaMap = @{}')
[void]$sb.AppendLine('function Get-FileHash { [CmdletBinding()] param($Path,$Algorithm); $p=[string]$Path; if ($script:__ShaMap.ContainsKey($p)) { return [pscustomobject]@{ Hash = $script:__ShaMap[$p] } }; return [pscustomobject]@{ Hash = ("A"*64) } }')

foreach ($name in $names) {
  $fn = Extract-FunctionText -Source $raw -Name $name
  if (-not $fn) { throw ("Required production helper missing or unextractable: {0}" -f $name) }
  [void]$sb.AppendLine($fn)
}

$script:__TempRoot = $(if ($env:TEMP) { $env:TEMP } elseif ($env:TMPDIR) { $env:TMPDIR } else { "/tmp" })
$tmp = Join-Path $script:__TempRoot ("hf3-v4-helpers-{0}.ps1" -f [guid]::NewGuid().ToString("N"))
Set-Content -LiteralPath $tmp -Value $sb.ToString() -Encoding UTF8
. $tmp

# --- Meta triad ---
$td = Join-Path $script:__TempRoot ("hf3-v4-meta-{0}" -f [guid]::NewGuid().ToString("N"))
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

# --- R1: Start foreign schema (production handler) ---
$script:__StopCalls = @(); $script:__StartCalls = @(); $script:__RemoveCalls = @()
Set-Content -LiteralPath $metaPath -Value '{"schema":"foreign","port":18878}' -Encoding UTF8
$threw = $false; $code = ""
try { Invoke-Hf3StartHandler -LaunchMetaPath $metaPath -PidPath $pidPath } catch { $threw = $true; $code = [string]$_.Exception.Message }
Assert-True ($threw -and $code -match "EXIT_START_INVALID_LAUNCH_META") "R1 Start blocks foreign schema"
Assert-True (Test-Path -LiteralPath $metaPath) "R1 meta preserved"
Assert-True ($script:__StartCalls.Count -eq 0) "R1 zero Start-Process"
Assert-True ($script:__StopCalls.Count -eq 0) "R1 zero Stop-Process"

# --- R2: Update foreign schema ---
$script:__RenameCalls = @(); $script:__RemoveCalls = @()
$threw = $false; $code = ""
try { Invoke-Hf3UpdateHandler -LaunchMetaPath $metaPath -PidPath $pidPath } catch { $threw = $true; $code = [string]$_.Exception.Message }
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
Microsoft.PowerShell.Management\Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
$script:__CimMap = @{
  2222 = [pscustomobject]@{ ProcessId = 2222; Name = "python.exe"; CommandLine = "python -m uvicorn app.main:app --host 127.0.0.1 --port 18878 --app-dir C:\HF3\backend"; CreationDate = $createDt; ExecutablePath = "C:\HF3\venv\Scripts\python.exe" }
}
$script:__TcpOwners = @()
$script:__StopCalls = @(); $script:__RemoveCalls = @()
$threw = $false; $code = ""
try { Invoke-Hf3StopHandler -LaunchMetaPath $metaPath -PidPath $pidPath -PortNum 18878 } catch { $threw = $true; $code = [string]$_.Exception.Message }
Assert-True ($threw -and $code -match "EXIT_STOP_STALE_LISTENER") "R3 Stop blocks off-port live listener"
Assert-True (Test-Path -LiteralPath $metaPath) "R3 meta preserved"
Assert-True ($script:__StopCalls.Count -eq 0) "R3 zero Stop-Process (no numeric kill)"

# --- R4: Update legacy pid live ---
Microsoft.PowerShell.Management\Remove-Item -LiteralPath $metaPath -Force -ErrorAction SilentlyContinue
$script:__CimMap = @{
  3333 = [pscustomobject]@{ ProcessId = 3333; Name = "python.exe"; CommandLine = "x"; CreationDate = $createDt; ExecutablePath = "C:\x\python.exe" }
}
Set-Content -LiteralPath $pidPath -Value "3333" -Encoding ASCII
Assert-True (-not (Test-Path -LiteralPath $metaPath)) "R4 setup: meta absent"
$threw = $false; $code = ""
try { Invoke-Hf3UpdateHandler -LaunchMetaPath $metaPath -PidPath $pidPath } catch { $threw = $true; $code = [string]$_.Exception.Message }
Assert-True ($threw -and $code -match "EXIT_UPDATE_BLOCKED_LEGACY_PID") ("R4 Update blocks live legacy pid (got={0})" -f $code)
Assert-True (Test-Path -LiteralPath $pidPath) "R4 legacy pid preserved"

# --- R8: Update launcher+listener live => zero stop ---
Set-Content -LiteralPath $metaPath -Value (@{
  schema = "mypc.hf3.launch.v1"; port = 18878; backend = "C:\HF3\backend"; host = "127.0.0.1"
  launcher_pid = 4444; launcher_creation = $createIso
  listener_pid = 5555; listener_creation = $createIso
  venv_python = "C:\HF3\venv\Scripts\python.exe"
} | ConvertTo-Json -Compress) -Encoding UTF8
Set-Content -LiteralPath $pidPath -Value "5555" -Encoding ASCII
$script:__CimMap = @{
  4444 = [pscustomobject]@{ ProcessId = 4444; Name = "python.exe"; CommandLine = "launcher"; CreationDate = $createDt; ExecutablePath = "C:\HF3\venv\Scripts\python.exe" }
  5555 = [pscustomobject]@{ ProcessId = 5555; Name = "python.exe"; CommandLine = "python -m uvicorn app.main:app --host 127.0.0.1 --port 18878 --app-dir C:\HF3\backend"; CreationDate = $createDt; ExecutablePath = "C:\HF3\venv\Scripts\python.exe" }
}
$script:__StopCalls = @(); $script:__RenameCalls = @()
$threw = $false; $code = ""
try { Invoke-Hf3UpdateHandler -LaunchMetaPath $metaPath -PidPath $pidPath } catch { $threw = $true; $code = [string]$_.Exception.Message }
Assert-True ($threw -and $code -match "EXIT_UPDATE_STALE_") "R8 Update blocks when launcher+listener live"
Assert-True ($script:__StopCalls.Count -eq 0) "R8 zero Stop-Process before listener gate"
Assert-True ($script:__RenameCalls.Count -eq 0) "R8 zero Rename-Item"

# --- V4.2 R9: Prepare refuses existing src (no Remove-Item of live src) ---
$prepRoot = Join-Path $td "cand-root"
$prepSrc = Join-Path $prepRoot "src"
$prepZip = Join-Path $td "full.zip"
$prepModels = Join-Path $td "models-src"
New-Item -ItemType Directory -Force -Path $prepSrc,$prepModels | Out-Null
Set-Content -LiteralPath $prepZip -Value "fake-zip" -Encoding ASCII
$script:__ShaMap[$prepZip] = ("b"*64)
$script:__TcpOwners = @()
$script:__RemoveCalls = @(); $script:__RenameCalls = @(); $script:__StopCalls = @()
Microsoft.PowerShell.Management\Remove-Item -LiteralPath $metaPath -Force -ErrorAction SilentlyContinue
Microsoft.PowerShell.Management\Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
$threw = $false; $code = ""
try {
  Invoke-Hf3PrepareHandler -FullSourceZipPath $prepZip -ExpectedSha ("b"*64) `
    -ModelsSourcePath $prepModels -CandidateRootPath $prepRoot `
    -SrcPath $prepSrc -LaunchMetaPath $metaPath -PidPath $pidPath -PortNum 18878
} catch { $threw = $true; $code = [string]$_.Exception.Message }
Assert-True ($threw -and $code -match "EXIT_PREPARE_EXISTING_SOURCE") "R9 Prepare refuses existing src"
Assert-True (Test-Path -LiteralPath $prepSrc) "R9 existing src preserved"
Assert-True ($script:__RemoveCalls.Count -eq 0) "R9 zero Remove-Item on refuse"
Assert-True ($script:__StopCalls.Count -eq 0) "R9 zero Stop-Process"

# --- V4.2 R9b: missing models source ---
Microsoft.PowerShell.Management\Remove-Item -Recurse -Force $prepSrc -ErrorAction SilentlyContinue
$threw = $false; $code = ""
try {
  Invoke-Hf3PrepareHandler -FullSourceZipPath $prepZip -ExpectedSha ("b"*64) `
    -ModelsSourcePath (Join-Path $td "missing-models") -CandidateRootPath $prepRoot `
    -SrcPath $prepSrc -LaunchMetaPath $metaPath -PidPath $pidPath -PortNum 18878
} catch { $threw = $true; $code = [string]$_.Exception.Message }
Assert-True ($threw -and $code -match "EXIT_PREPARE_INPUT_INVALID" -and $code -match "ModelsSourceDir") "R9b Prepare missing models"

# --- V4.2 R9c: protected / aliased candidate root ---
$threw = $false; $code = ""
try { Assert-Hf3CandidateRootSafe "C:\lab\p02-usb-hf1-stable" } catch { $threw = $true; $code = [string]$_.Exception.Message }
Assert-True ($threw -and $code -match "EXIT_PREPARE_INPUT_INVALID") "R9c protected HF1 root refused"
$threw = $false; $code = ""
try { Assert-Hf3CandidateRootSafe "D:\owner\18876\DataDir" } catch { $threw = $true; $code = [string]$_.Exception.Message }
Assert-True ($threw -and $code -match "EXIT_PREPARE_INPUT_INVALID") "R9c 18876 overlap refused"

# --- V4.2 R9d: live listener on Prepare ---
New-Item -ItemType Directory -Force -Path $prepModels | Out-Null
$script:__TcpOwners = @(4242)
$script:__StopCalls = @()
$threw = $false; $code = ""
try {
  Invoke-Hf3PrepareHandler -FullSourceZipPath $prepZip -ExpectedSha ("b"*64) `
    -ModelsSourcePath $prepModels -CandidateRootPath $prepRoot `
    -SrcPath $prepSrc -LaunchMetaPath $metaPath -PidPath $pidPath -PortNum 18878
} catch { $threw = $true; $code = [string]$_.Exception.Message }
Assert-True ($threw -and $code -match "EXIT_PREPARE_PROCESS_UNKNOWN") "R9d Prepare refuses live listener"
Assert-True ($script:__StopCalls.Count -eq 0) "R9d zero Stop-Process"
$script:__TcpOwners = @()

# --- V4.2 R9e: positive fresh Prepare authorization ---
$okPrep = Invoke-Hf3PrepareHandler -FullSourceZipPath $prepZip -ExpectedSha ("b"*64) `
  -ModelsSourcePath $prepModels -CandidateRootPath $prepRoot `
  -SrcPath $prepSrc -LaunchMetaPath $metaPath -PidPath $pidPath -PortNum 18878
Assert-True ($okPrep.Ok -eq $true) "R9e fresh Prepare authorized"
Assert-True ($script:__RemoveCalls.Count -eq 0) "R9e authorization does not mutate"

# --- V4.2 R10: meta valid + unexpected live uvicorn.pid ---
Set-Content -LiteralPath $metaPath -Value (@{
  schema = "mypc.hf3.launch.v1"; port = 18878; backend = "C:\HF3\backend"; host = "127.0.0.1"
  launcher_pid = 4444; launcher_creation = $createIso
  listener_pid = 5555; listener_creation = $createIso
  venv_python = "C:\HF3\venv\Scripts\python.exe"
} | ConvertTo-Json -Compress) -Encoding UTF8
Set-Content -LiteralPath $pidPath -Value "4242" -Encoding ASCII
$script:__CimMap = @{
  4242 = [pscustomobject]@{ ProcessId = 4242; Name = "python.exe"; CommandLine = "foreign"; CreationDate = $createDt; ExecutablePath = "C:\x\python.exe" }
}
$pidBad = Test-Hf3PidRecord -PidPath $pidPath -Meta (Get-Hf3LaunchMetaState $metaPath).Meta
Assert-True (-not $pidBad.Ok -and $pidBad.Status -eq "MISMATCH") "R10 unexpected pid vs meta => MISMATCH"
$threw = $false; $code = ""
try { Invoke-Hf3StartHandler -LaunchMetaPath $metaPath -PidPath $pidPath } catch { $threw = $true; $code = [string]$_.Exception.Message }
Assert-True ($threw -and $code -match "EXIT_START_PID_RECORD_INCONSISTENT") "R10 Start refuses pid mismatch"
Assert-True (Test-Path -LiteralPath $pidPath) "R10 pid file preserved"
Assert-True ($script:__StopCalls.Count -eq 0) "R10 zero Stop-Process"

# --- V4.2 R10b: malformed pid ---
Set-Content -LiteralPath $pidPath -Value "not-an-int" -Encoding ASCII
$stMal = Get-Hf3PidRecordState $pidPath
Assert-True ($stMal.Status -eq "INVALID") "R10b malformed pid => INVALID"

# --- V4.2 R10c: positive stale absent pid with meta (safe CLEAR) ---
Microsoft.PowerShell.Management\Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
$script:__CimMap = @{}
$staleOk = Invoke-Hf3StartHandler -LaunchMetaPath $metaPath -PidPath $pidPath
Assert-True ($staleOk.Action -eq "CLEAR_STALE_META") "R10c Start authorizes CLEAR_STALE_META when identities absent"
Assert-True ($script:__StopCalls.Count -eq 0) "R10c zero Stop-Process on stale clear auth"

# Coverage markers: production handlers extracted (R12), not synthetic facades
$harnessSelf = Get-Content -LiteralPath $PSCommandPath -Raw -Encoding UTF8
Assert-True ($harnessSelf -match 'Extract-ModeText') "R12 harness Extract-ModeText present"
Assert-True ($harnessSelf -match 'Invoke-Hf3PrepareHandler') "Harness covers Invoke-Hf3PrepareHandler"
Assert-True ($harnessSelf -match 'Invoke-Hf3StopHandler') "Harness covers Invoke-Hf3StopHandler"
Assert-True ($harnessSelf -match 'Invoke-Hf3UpdateHandler') "Harness covers Invoke-Hf3UpdateHandler"
Assert-True ($harnessSelf -match 'Stop-VerifiedHf3LaunchTree') "Harness extracts Stop-VerifiedHf3LaunchTree"
Assert-True ($null -ne $script:__PrepareModeBody -and $script:__PrepareModeBody -match 'Invoke-Hf3PrepareHandler') "R12 Prepare mode body invokes production handler"
Assert-True (-not ($harnessSelf -match '(?s)function Invoke-Hf3StartHandler\s*\{')) "R12 harness does not redefine Start facade"

Assert-True ($script:__StartCalls.Count -eq 0) "No Start-Process on negative handler cases"

Microsoft.PowerShell.Management\Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
Microsoft.PowerShell.Management\Remove-Item -Recurse -Force $td -ErrorAction SilentlyContinue
if ($failed -gt 0) { Write-Host "RESULT: $failed failed" -ForegroundColor Red; exit 1 }
Write-Host "RESULT: PASS (V4.2 injected fail-closed behavioral; production handlers; no real kill/Start)" -ForegroundColor Green
exit 0
