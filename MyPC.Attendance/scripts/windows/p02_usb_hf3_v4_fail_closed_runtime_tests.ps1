#Requires -Version 5.1
<#
.SYNOPSIS
  Injected fail-closed behavioral tests for HF3 V4 (no real CIM/TCP/kill/Start).

.DESCRIPTION
  Extracts pure helpers, injects fake Get-CimInstance / Get-NetTCPConnection /
  Stop-Process / Start-Process boundaries. Never touches owner HF3,
  ports 18876/18877, cameras, or DataDir. Exit 0 = PASS.
#>
$ErrorActionPreference = "Stop"
$failed = 0
function Assert-True([bool]$Cond, [string]$Msg) {
  if (-not $Cond) { Write-Host "FAIL: $Msg" -ForegroundColor Red; $script:failed++ }
  else { Write-Host "PASS: $Msg" -ForegroundColor Green }
}

function Extract-FunctionText([string]$Source, [string]$Name) {
  # Match "function Name" then first "{" even when param(...) sits between.
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
  "Test-IsPythonProcessName",
  "Test-IsConhostName",
  "Test-Hf3UvicornCommandLine",
  "Split-Hf3WindowsCommandLine",
  "Get-Win32ProcessById",
  "Get-Hf3PortListenerOwnerPids"
)

$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine('$script:__CimThrow = $false')
[void]$sb.AppendLine('$script:__TcpThrow = $false')
[void]$sb.AppendLine('$script:__CimMap = @{}')
[void]$sb.AppendLine('$script:__TcpOwners = @()')
[void]$sb.AppendLine('$script:__StopCalls = @()')
[void]$sb.AppendLine('$script:__StartCalls = @()')
# Never declare -ErrorAction on mocks: it collides with PowerShell common parameters.
[void]$sb.AppendLine('function Get-CimInstance { [CmdletBinding()] param($ClassName,$Filter); if ($script:__CimThrow) { throw "access denied" }; $id=0; if ($Filter -match "ProcessId=(\d+)") { $id=[int]$Matches[1] }; if ($script:__CimMap.ContainsKey($id)) { return $script:__CimMap[$id] }; return $null }')
[void]$sb.AppendLine('function Get-NetTCPConnection { [CmdletBinding()] param($LocalPort,$State); if ($script:__TcpThrow) { throw "provider timeout" }; if ($script:__TcpOwners.Count -eq 0) { throw "No MSFT_NetTCPConnection objects found" }; return @($script:__TcpOwners | ForEach-Object { [pscustomobject]@{ OwningProcess = $_ } }) }')
[void]$sb.AppendLine('function Stop-Process { [CmdletBinding()] param($Id,[switch]$Force); $script:__StopCalls += $Id; throw "mocked-stop-should-not-run-on-negatives" }')
[void]$sb.AppendLine('function Start-Process { [CmdletBinding()] param($FilePath,$ArgumentList,$WorkingDirectory,$RedirectStandardOutput,$RedirectStandardError,[switch]$PassThru,$WindowStyle); $script:__StartCalls += ,@($FilePath,$ArgumentList); return [pscustomobject]@{ Id = 99991 } }')
[void]$sb.AppendLine('function Write-Log([string]$Message) { Write-Host ("[v4] " + $Message) }')

foreach ($name in $names) {
  $fn = Extract-FunctionText -Source $raw -Name $name
  if (-not $fn) { throw ("Required helper missing or unextractable: {0}" -f $name) }
  [void]$sb.AppendLine($fn)
}

$tmp = Join-Path $env:TEMP ("hf3-v4-helpers-{0}.ps1" -f [guid]::NewGuid().ToString("N"))
Set-Content -LiteralPath $tmp -Value $sb.ToString() -Encoding UTF8
. $tmp

# --- Meta triad ---
$td = Join-Path $env:TEMP ("hf3-v4-meta-{0}" -f [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $td | Out-Null
$metaPath = Join-Path $td "uvicorn.launch.json"
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
Assert-True ($stVal.State -eq "VALID") "Parseable JSON => VALID"

# --- Process probe UNKNOWN ---
$script:__CimThrow = $true
$threw = $false
try { [void](Get-Win32ProcessById 4242) } catch { $threw = ($_.Exception.Message -match "EXIT_PROCESS_PROBE_UNKNOWN") }
Assert-True $threw "CIM failure => EXIT_PROCESS_PROBE_UNKNOWN (not silent null)"
$script:__CimThrow = $false
Assert-True ($null -eq (Get-Win32ProcessById 4242)) "Missing process => null ABSENT"

# --- TCP probe UNKNOWN vs free ---
$script:__TcpThrow = $true
$threw = $false
try { [void](Get-Hf3PortListenerOwnerPids 18878) } catch { $threw = ($_.Exception.Message -match "EXIT_TCP_PROBE_UNKNOWN") }
Assert-True $threw "TCP provider failure => EXIT_TCP_PROBE_UNKNOWN"
$script:__TcpThrow = $false
$script:__TcpOwners = @()
$free = @(Get-Hf3PortListenerOwnerPids 18878)
Assert-True ($free.Count -eq 0) "No listener MSFT object => free port ABSENT"

# --- Argv quoting with spaces ---
$line = Format-Hf3UvicornProcessArguments -Backend 'C:\Users\Test User\backend' -PortNum 18878
Assert-True ($line -match '"C:\\Users\\Test User\\backend"') "app-dir with spaces is quoted as one token"

Assert-True ($script:__StopCalls.Count -eq 0) "No Stop-Process on negative probe cases"
Assert-True ($script:__StartCalls.Count -eq 0) "No Start-Process on negative probe cases"

Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $td -ErrorAction SilentlyContinue
if ($failed -gt 0) { Write-Host "RESULT: $failed failed" -ForegroundColor Red; exit 1 }
Write-Host "RESULT: PASS (V4 injected fail-closed behavioral; no real kill/Start)" -ForegroundColor Green
exit 0
