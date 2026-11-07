#Requires -Version 5.1
<#
.SYNOPSIS
  Isolated Windows PowerShell 5.1 runtime checks for HF3 PID-safety helpers.

.DESCRIPTION
  Default mode is FULLY MOCKED:
  - Get-Win32ProcessById is injected
  - Stop-Process is replaced with a recording double that NEVER calls the real cmdlet
  - No hardcoded synthetic PID is passed to a real OS termination API

  Optional -RunSyntheticLab (explicit opt-in only):
  - Requires a free throwaway loopback port (default 18991; never 18876/18877/18878)
  - Starts a short-lived HTTP server via CandidateRoot venv python when available
  - Issues a real health request, records launcher/child identity, then tears down
    in finally and verifies port release. Never claims USB physical PASS.

  Does NOT Prepare/Start the attendance HF3 candidate, open a camera, or touch HMAC.
#>
param(
  [string]$CandidateScript = (Join-Path $PSScriptRoot "p02_usb_hf3_candidate_18878.ps1"),
  [switch]$RunSyntheticLab,
  [string]$CandidateRoot = "$env:LOCALAPPDATA\MyPC.Attendance\p02-usb-hf3-candidate",
  [int]$SyntheticPort = 18991
)

$ErrorActionPreference = "Stop"
$failed = 0
function Assert-True([bool]$Cond, [string]$Msg) {
  if (-not $Cond) {
    Write-Host "FAIL: $Msg" -ForegroundColor Red
    $script:failed++
  } else {
    Write-Host "PASS: $Msg" -ForegroundColor Green
  }
}

if (-not (Test-Path -LiteralPath $CandidateScript)) {
  throw "Candidate script missing: $CandidateScript"
}
if (@(18876, 18877, 18878) -contains $SyntheticPort) {
  throw "SyntheticPort must not reuse HF3/legacy ports"
}

# --- Static source contracts ---
$raw = Get-Content -LiteralPath $CandidateScript -Raw -Encoding UTF8
Assert-True (-not ($raw -match '(?i)\bforeach\s*\(\s*\$pid\b')) "No foreach(`$pid) collision with automatic `$PID"
Assert-True ($raw -match 'function Stop-VerifiedHf3Identity') "Stop-VerifiedHf3Identity present"
Assert-True ($raw -match 'launcher_creation') "launcher_creation persisted"
Assert-True ($raw -notmatch '\$venvMarker') "No `$venvMarker kill authorization"
Assert-True ($raw -match 'EXIT_STOP_BLOCKED_LEGACY_PID') "Legacy PID-only stop blocked"
Assert-True ($raw -notmatch '\$CommandLine\.IndexOf\(\$backendNorm') "No IndexOf backend substring fallback"

# --- Extract helpers into isolated scope with DI mocks ---
$helperNames = @(
  "Test-Hf3UvicornCommandLine",
  "Split-Hf3WindowsCommandLine",
  "Get-Hf3OptionValues",
  "Test-IsPythonProcessName",
  "Test-IsConhostName",
  "Test-Hf3LaunchMetaSchema",
  "Test-LiveMatchesLaunchMeta",
  "Stop-VerifiedHf3Identity",
  "Stop-VerifiedHf3LaunchTree",
  "Test-Hf3HealthStartPass",
  "Write-Log"
)

$stub = @'
function Write-Log([string]$Message) { Write-Host ("[hf3-runtime-test] " + $Message) }
$script:__InjectedProcs = @{}
$script:__StopProcessCalls = New-Object System.Collections.Generic.List[object]
$script:__RealStopProcess = $null
function Get-Win32ProcessById([int]$ProcessId) {
  if ($script:__InjectedProcs.ContainsKey($ProcessId)) { return $script:__InjectedProcs[$ProcessId] }
  return $null
}
# CRITICAL: never call the real Stop-Process cmdlet from default tests.
function Stop-Process {
  param(
    [Parameter(Mandatory=$true)][int]$Id,
    [switch]$Force,
    [System.Management.Automation.ActionPreference]$ErrorAction = $ErrorActionPreference
  )
  $script:__StopProcessCalls.Add([pscustomobject]@{ Id = $Id; Force = [bool]$Force; Utc = (Get-Date).ToUniversalTime().ToString("o") }) | Out-Null
  # Simulate success by removing the injected process only (never touch OS).
  if ($script:__InjectedProcs.ContainsKey($Id)) {
    $script:__InjectedProcs.Remove($Id) | Out-Null
  }
}
'@

$extracted = New-Object System.Text.StringBuilder
[void]$extracted.AppendLine($stub)
foreach ($name in $helperNames) {
  if ($name -eq "Write-Log") { continue }
  $pattern = "(?s)function\s+$([regex]::Escape($name))\s*\{"
  $m = [regex]::Match($raw, $pattern)
  if (-not $m.Success) {
    Write-Host "WARN: helper $name not found for extract" -ForegroundColor Yellow
    continue
  }
  $start = $m.Index
  $depth = 0
  $i = $raw.IndexOf("{", $start)
  for (; $i -lt $raw.Length; $i++) {
    $ch = $raw[$i]
    if ($ch -eq "{") { $depth++ }
    elseif ($ch -eq "}") {
      $depth--
      if ($depth -eq 0) {
        [void]$extracted.AppendLine($raw.Substring($start, $i - $start + 1))
        break
      }
    }
  }
}

$tmp = Join-Path $env:TEMP ("hf3-pid-safety-helpers-{0}.ps1" -f [guid]::NewGuid().ToString("N"))
# UTF-8 with BOM for PS 5.1
$utf8Bom = New-Object System.Text.UTF8Encoding $true
[System.IO.File]::WriteAllText($tmp, $extracted.ToString(), $utf8Bom)
. $tmp

$backend = "C:\Users\Owner\AppData\Local\MyPC.Attendance\p02-usb-hf3-candidate\src\backend"
$backendSpaced = "C:\Users\Owner\AppData\Local\MyPC.Attendance\p02-usb-hf3-candidate\src\MyPC Attendance\backend"
$goodCmd = "`"C:\Python\python.exe`" -m uvicorn app.main:app --host 127.0.0.1 --port 18878 --app-dir $backend"
$goodCmdSpaced = "`"C:\Python\python.exe`" -m uvicorn app.main:app --host 127.0.0.1 --port 18878 --app-dir `"$backendSpaced`""
$foreignAppDirCmd = "`"C:\Python\python.exe`" -m uvicorn app.main:app --host 127.0.0.1 --port 18878 --app-dir C:\ForeignService\backend --log-config `"$backend\logging.ini`""
$wrongPortCmd = "`"C:\Python\python.exe`" -m uvicorn app.main:app --host 127.0.0.1 --port 188780 --app-dir $backend"
$prefixCmd = "`"C:\Python\python.exe`" -m uvicorn app.main:app --host 127.0.0.1 --port 18878 --app-dir ${backend}2"

Assert-True ((Test-Hf3UvicornCommandLine -CommandLine $goodCmd -Backend $backend -PortNum 18878) -eq $true) "Exact tokenized cmdline accepted"
Assert-True ((Test-Hf3UvicornCommandLine -CommandLine $goodCmdSpaced -Backend $backendSpaced -PortNum 18878) -eq $true) "Quoted path with spaces accepted"
Assert-True ((Test-Hf3UvicornCommandLine -CommandLine $foreignAppDirCmd -Backend $backend -PortNum 18878) -eq $false) "Foreign --app-dir rejected despite HF3 path elsewhere"
Assert-True ((Test-Hf3UvicornCommandLine -CommandLine $wrongPortCmd -Backend $backend -PortNum 18878) -eq $false) "Wrong port 188780 rejected"
Assert-True ((Test-Hf3UvicornCommandLine -CommandLine $prefixCmd -Backend $backend -PortNum 18878) -eq $false) "backend2 prefix rejected"
Assert-True ((Test-Hf3UvicornCommandLine -CommandLine "note uvicorn 18878 path $backend" -Backend $backend -PortNum 18878) -eq $false) "Loose substring rejected"

$createIso = ([datetime]::Parse("2026-11-07T01:00:00Z")).ToUniversalTime().ToString("o")
# Synthetic fixture PID lives only in the injection map; Stop-Process is mocked.
# Never pass a bare numeric literal into production stop helpers in a way static
# audits can confuse with a real OS kill (use a variable + mocked cmdlet).
$synthListenerPid = 4242
$synthConhostPid = 5151
$script:__InjectedProcs[$synthListenerPid] = [pscustomobject]@{
  ProcessId = $synthListenerPid; Name = "python.exe"; CommandLine = $goodCmd
  ExecutablePath = "C:\Python\python.exe"; CreationDate = [datetime]::Parse("2026-11-07T01:00:00Z")
  ParentProcessId = 1
}
$script:__StopProcessCalls.Clear()

# Identity allow → mocked Stop-Process records call; never touches a real OS process.
$ok = Stop-VerifiedHf3Identity -TargetPid $synthListenerPid -ExpectedCreation $createIso -Backend $backend -PortNum 18878 -Role "listener"
Assert-True ($ok -eq $true) "Mocked verified listener stop returns true"
Assert-True ($script:__StopProcessCalls.Count -eq 1) "Exactly one mocked Stop-Process call recorded"
Assert-True ([int]$script:__StopProcessCalls[0].Id -eq $synthListenerPid) "Mock recorded synthetic TargetPid"
Assert-True (-not $script:__InjectedProcs.ContainsKey($synthListenerPid)) "Injected process removed by mock only"

# Re-inject for refusal cases — Stop-Process must NOT be called.
$script:__InjectedProcs[$synthListenerPid] = [pscustomobject]@{
  ProcessId = $synthListenerPid; Name = "python.exe"; CommandLine = $goodCmd
  ExecutablePath = "C:\Python\python.exe"; CreationDate = [datetime]::Parse("2026-11-07T01:00:00Z")
  ParentProcessId = 1
}
$before = $script:__StopProcessCalls.Count
$badCreate = Stop-VerifiedHf3Identity -TargetPid $synthListenerPid -ExpectedCreation "WRONG" -Backend $backend -PortNum 18878 -Role "listener"
Assert-True ($badCreate -eq $false) "Creation mismatch refuses kill"
Assert-True ($script:__StopProcessCalls.Count -eq $before) "No Stop-Process on creation mismatch"

$blankCreate = Stop-VerifiedHf3Identity -TargetPid $synthListenerPid -ExpectedCreation "" -Backend $backend -PortNum 18878 -Role "listener"
Assert-True ($blankCreate -eq $false) "Blank creation refuses kill"
Assert-True ($script:__StopProcessCalls.Count -eq $before) "No Stop-Process on blank creation"

$script:__InjectedProcs[$synthConhostPid] = [pscustomobject]@{
  ProcessId = $synthConhostPid; Name = "conhost.exe"; CommandLine = "conhost"; ExecutablePath = "C:\Windows\System32\conhost.exe"
  CreationDate = [datetime]::Parse("2026-11-07T01:00:00Z"); ParentProcessId = $synthListenerPid
}
$con = Stop-VerifiedHf3Identity -TargetPid $synthConhostPid -ExpectedCreation $createIso -Backend $backend -PortNum 18878 -Role "listener"
Assert-True ($con -eq $false) "conhost never killed"
Assert-True ($script:__StopProcessCalls.Count -eq $before) "No Stop-Process for conhost"

# Adversarial: pick a real OS process PID (this shell) and ensure we never call Stop-Process for it
# when injection map has no entry / identity refuses.
$realPid = $PID
$beforeAdv = $script:__StopProcessCalls.Count
$adv = Stop-VerifiedHf3Identity -TargetPid $realPid -ExpectedCreation "no-such-creation" -Backend $backend -PortNum 18878 -Role "listener"
Assert-True ($adv -eq $false) "Unrelated real PID refused without matching injection+creation"
Assert-True ($script:__StopProcessCalls.Count -eq $beforeAdv) "Adversarial: real PID never reached mocked Stop-Process"
# Extra: even if someone injected the real PID with wrong cmdline, creation mismatch still blocks.
$script:__InjectedProcs[$realPid] = [pscustomobject]@{
  ProcessId = $realPid; Name = "powershell.exe"; CommandLine = "not-uvicorn"; ExecutablePath = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
  CreationDate = [datetime]::Parse("2026-11-07T01:00:00Z"); ParentProcessId = 1
}
$beforeAdv2 = $script:__StopProcessCalls.Count
$adv2 = Stop-VerifiedHf3Identity -TargetPid $realPid -ExpectedCreation $createIso -Backend $backend -PortNum 18878 -Role "listener"
Assert-True ($adv2 -eq $false) "Injected real PID with foreign cmdline refused"
Assert-True ($script:__StopProcessCalls.Count -eq $beforeAdv2) "Adversarial: foreign real PID not signaled"
$script:__InjectedProcs.Remove($realPid) | Out-Null

$healthBad = Test-Hf3HealthStartPass -StatusCode 200 -Body '{"status":"degraded","startup_phase":"FAIL","x":{"status":"ok","startup_phase":"READY"}}'
Assert-True ($healthBad -eq $false) "Nested ok/READY rejected"
$healthOk = Test-Hf3HealthStartPass -StatusCode 200 -Body '{"status":"ok","startup_phase":"READY"}'
Assert-True ($healthOk -eq $true) "Top-level ok+READY accepted"

$metaBad = [pscustomobject]@{ schema = "mypc.hf3.launch.v1"; port = 18878; backend = $backend; listener_pid = 4242; listener_creation = "" }
Assert-True ((Test-Hf3LaunchMetaSchema $metaBad) -eq $false) "Blank listener_creation fails schema"

# --- Optional synthetic lab (explicit -RunSyntheticLab only) ---
if ($RunSyntheticLab) {
  $venvPy = Join-Path $CandidateRoot "venv\Scripts\python.exe"
  if (-not (Test-Path $venvPy)) {
    Write-Host "SKIP synthetic lab — venv missing at $CandidateRoot" -ForegroundColor Yellow
  } else {
    $busy = @(Get-NetTCPConnection -LocalPort $SyntheticPort -State Listen -ErrorAction SilentlyContinue)
    Assert-True ($busy.Count -eq 0) ("Synthetic port {0} must be free before lab" -f $SyntheticPort)
    if ($busy.Count -eq 0) {
      $pyCode = @"
import http.server, socketserver, json, sys
PORT = int(sys.argv[1])
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({'status':'ok','startup_phase':'READY'}).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a):
        pass
httpd = socketserver.TCPServer(('127.0.0.1', PORT), H)
httpd.timeout = 15
httpd.handle_request()
"@
      $proc = $null
      $childPids = @()
      try {
        $proc = Start-Process -FilePath $venvPy -ArgumentList @("-c", $pyCode, "$SyntheticPort") -PassThru -WindowStyle Hidden
        $deadline = (Get-Date).AddSeconds(10)
        $listening = $false
        while ((Get-Date) -lt $deadline) {
          $ls = @(Get-NetTCPConnection -LocalPort $SyntheticPort -State Listen -ErrorAction SilentlyContinue)
          if ($ls.Count -gt 0) { $listening = $true; $childPids = @($ls | ForEach-Object { [int]$_.OwningProcess } | Select-Object -Unique); break }
          Start-Sleep -Milliseconds 200
        }
        Assert-True $listening ("Synthetic lab listening on 127.0.0.1:{0}" -f $SyntheticPort)
        $r = Invoke-WebRequest -Uri ("http://127.0.0.1:{0}/" -f $SyntheticPort) -UseBasicParsing -TimeoutSec 5
        Assert-True ([int]$r.StatusCode -eq 200) "Synthetic health HTTP 200"
        Assert-True ($r.Content -match '"status"\s*:\s*"ok"') "Synthetic health status ok"
        $launcher = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $proc.Id) -ErrorAction SilentlyContinue
        Assert-True ($null -ne $launcher -or $proc.HasExited) "Launcher identity probed"
        Write-Host ("SYNTH launcher_pid={0} child_pids={1}" -f $proc.Id, ($childPids -join ','))
      } finally {
        foreach ($cp in $childPids) {
          if ($cp -gt 0 -and $cp -ne [int]$proc.Id) {
            # Only stop children that still own our synthetic port (verified ownership of THIS lab).
            $still = @(Get-NetTCPConnection -LocalPort $SyntheticPort -State Listen -ErrorAction SilentlyContinue |
              Where-Object { [int]$_.OwningProcess -eq $cp })
            if ($still.Count -gt 0) {
              try { Microsoft.PowerShell.Management\Stop-Process -Id $cp -Force -ErrorAction SilentlyContinue } catch {}
            }
          }
        }
        if ($proc -and -not $proc.HasExited) {
          try { Microsoft.PowerShell.Management\Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
        }
        Start-Sleep -Milliseconds 300
        if ($proc) {
          try { $proc.Refresh() } catch {}
          Assert-True ($proc.HasExited) "Synthetic launcher exited after teardown"
        }
        $left = @(Get-NetTCPConnection -LocalPort $SyntheticPort -State Listen -ErrorAction SilentlyContinue)
        Assert-True ($left.Count -eq 0) ("Synthetic port {0} released after teardown" -f $SyntheticPort)
      }
    }
  }
}

Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
if ($failed -gt 0) {
  Write-Host "RESULT: $failed assertion(s) failed" -ForegroundColor Red
  exit 1
}
Write-Host "RESULT: PASS (Windows PS 5.1 PID-safety runtime checks; Stop-Process mocked by default)" -ForegroundColor Green
exit 0
