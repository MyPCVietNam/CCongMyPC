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
  "Split-Hf3WindowsCommandLine",
  "Get-Hf3OptionValues",
  "Test-Hf3UvicornCommandLine",
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
  # Allow param(...) between name and '{' (PS 5.1 / Windows CI).
  $pattern = "(?s)function\s+$([regex]::Escape($name))\b[^{]*\{"
  $m = [regex]::Match($raw, $pattern)
  if (-not $m.Success) {
    throw ("Required helper missing or unextractable: {0}" -f $name)
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

$cmdOk = Test-Hf3UvicornCommandLine -CommandLine $goodCmd -Backend $backend -PortNum 18878
if (-not $cmdOk) {
  $dbgArgs = @(Split-Hf3WindowsCommandLine $goodCmd)
  Write-Host ("DBG goodCmd argv({0}): {1}" -f $dbgArgs.Count, ($dbgArgs -join ' || ')) -ForegroundColor Yellow
}
Assert-True ($cmdOk -eq $true) "Exact tokenized cmdline accepted"
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

# --- Optional synthetic lab (explicit -RunSyntheticLab + env approval only) ---
# NEVER calls a real Stop-Process / kill API. One-shot HTTP server exits after the request.
# Disabled unless MYPC_HF3_SYNTHETIC_LAB_APPROVED=1 on an isolated CI host (not owner workstation).
if ($RunSyntheticLab) {
  if ($env:MYPC_HF3_SYNTHETIC_LAB_APPROVED -ne "1") {
    Write-Host "SKIP synthetic lab — set MYPC_HF3_SYNTHETIC_LAB_APPROVED=1 only on isolated CI (never owner HF3/USB)" -ForegroundColor Yellow
  } else {
    $venvPy = Join-Path $CandidateRoot "venv\Scripts\python.exe"
    if (-not (Test-Path $venvPy)) {
      Write-Host "SKIP synthetic lab — venv missing at $CandidateRoot" -ForegroundColor Yellow
    } else {
      $busy = @(Get-NetTCPConnection -LocalPort $SyntheticPort -State Listen -ErrorAction SilentlyContinue)
      Assert-True ($busy.Count -eq 0) ("Synthetic port {0} must be free before lab" -f $SyntheticPort)
      if ($busy.Count -eq 0) {
        $pyFile = Join-Path $env:TEMP ("hf3-synth-lab-{0}.py" -f [guid]::NewGuid().ToString("N"))
        $pyBody = @"
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
        Set-Content -LiteralPath $pyFile -Value $pyBody -Encoding ASCII
        $proc = $null
        $spawnCreation = ""
        $spawnCmd = ""
        try {
          $proc = Start-Process -FilePath $venvPy -ArgumentList @($pyFile, "$SyntheticPort") -PassThru -WindowStyle Hidden
          $spawnSnap = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $proc.Id) -ErrorAction SilentlyContinue
          if ($spawnSnap) {
            $spawnCreation = [string]$spawnSnap.CreationDate
            $spawnCmd = [string]$spawnSnap.CommandLine
          }
          Assert-True ($null -ne $spawnSnap) "Synthetic lab captured launcher CreationDate + CommandLine at spawn"
          $deadline = (Get-Date).AddSeconds(10)
          $listening = $false
          $childPids = @()
          while ((Get-Date) -lt $deadline) {
            $ls = @(Get-NetTCPConnection -LocalPort $SyntheticPort -State Listen -ErrorAction SilentlyContinue)
            if ($ls.Count -gt 0) {
              $listening = $true
              $childPids = @($ls | ForEach-Object { [int]$_.OwningProcess } | Select-Object -Unique)
              break
            }
            Start-Sleep -Milliseconds 200
          }
          Assert-True $listening ("Synthetic lab listening on 127.0.0.1:{0}" -f $SyntheticPort)
          # Prove listener identity matches self-spawned tree (creation/cmdline), never kill by port alone.
          foreach ($cp in $childPids) {
            $lp = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $cp) -ErrorAction SilentlyContinue
            Assert-True ($null -ne $lp) ("Synthetic listener pid={0} still enumerable" -f $cp)
            Assert-True ([string]$lp.CreationDate -ne "") ("Synthetic listener pid={0} has CreationDate" -f $cp)
            Assert-True ([string]$lp.CommandLine -match [regex]::Escape($pyFile) -or $cp -eq [int]$proc.Id) (
              "Synthetic listener cmdline must reference spawned script or be launcher itself"
            )
          }
          $r = Invoke-WebRequest -Uri ("http://127.0.0.1:{0}/" -f $SyntheticPort) -UseBasicParsing -TimeoutSec 5
          Assert-True ([int]$r.StatusCode -eq 200) "Synthetic health HTTP 200"
          Assert-True ($r.Content -match '"status"\s*:\s*"ok"') "Synthetic health status ok"
          Write-Host ("SYNTH launcher_pid={0} create={1} child_pids={2}" -f $proc.Id, $spawnCreation, ($childPids -join ','))
          # Wait for natural exit after one-shot handle_request — no real Stop-Process.
          $exitDeadline = (Get-Date).AddSeconds(10)
          while ((Get-Date) -lt $exitDeadline) {
            try { $proc.Refresh() } catch {}
            if ($proc.HasExited) { break }
            Start-Sleep -Milliseconds 200
          }
          Assert-True ($proc.HasExited) "Synthetic launcher exited naturally after single request (no kill)"
          $left = @(Get-NetTCPConnection -LocalPort $SyntheticPort -State Listen -ErrorAction SilentlyContinue)
          Assert-True ($left.Count -eq 0) ("Synthetic port {0} released without Stop-Process" -f $SyntheticPort)
        } finally {
          # Fail closed: never call real Stop-Process here even if processes linger.
          if ($proc -and -not $proc.HasExited) {
            Write-Host "FAIL: synthetic process still live — refusing kill; mark lab FAILED" -ForegroundColor Red
            $script:failed++
          }
          Remove-Item -LiteralPath $pyFile -Force -ErrorAction SilentlyContinue
        }
      }
    }
  }
}
# Contract: harness must not contain a real qualified process-kill cmdlet invocation.
# Build the forbidden token without embedding a greppable kill cmdlet path in source comments.
$forbiddenKill = 'Microsoft' + '.PowerShell.Management' + [char]92 + 'Stop-Process'
$harnessSelf = Get-Content -LiteralPath $MyInvocation.MyCommand.Path -Raw -Encoding UTF8
Assert-True ($harnessSelf.IndexOf($forbiddenKill, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) "Harness has no real qualified Stop-Process kill cmdlet"
Assert-True ($harnessSelf -match '(?i)function Stop-Process') "Harness defines Stop-Process mock only"

Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
if ($failed -gt 0) {
  Write-Host "RESULT: $failed assertion(s) failed" -ForegroundColor Red
  exit 1
}
Write-Host "RESULT: PASS (Windows PS 5.1 PID-safety runtime checks; Stop-Process mocked by default)" -ForegroundColor Green
exit 0
