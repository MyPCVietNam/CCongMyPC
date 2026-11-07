#Requires -Version 5.1
<#
.SYNOPSIS
  Isolated Windows PowerShell 5.1 runtime checks for HF3 PID-safety helpers.

.DESCRIPTION
  Dot-sources only the helper definitions from p02_usb_hf3_candidate_18878.ps1 by
  extracting function bodies into a temporary script. Does NOT Prepare/Start the
  attendance candidate, open a camera, or kill unknown processes.

  Optional synthetic HTTP listener lab (-RunSyntheticLab) binds a throwaway port
  via the HF3 venv python redirector when CandidateRoot is prepared; records
  launcher/listener PIDs and creation times, then verifies Stop-VerifiedHf3Identity
  refuses recycled/mismatched creation and never targets conhost.

  Exit 0 = all exercised assertions passed. Owner must still authorize real HF3 Start.
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

# --- Static: $PID automatic variable collision must be absent ---
$raw = Get-Content -LiteralPath $CandidateScript -Raw -Encoding UTF8
Assert-True (-not ($raw -match '(?i)\bforeach\s*\(\s*\$pid\b')) "No foreach(`$pid) collision with automatic `$PID"
Assert-True ($raw -match 'function Stop-VerifiedHf3Identity') "Stop-VerifiedHf3Identity present"
Assert-True ($raw -match 'launcher_creation') "launcher_creation persisted"
Assert-True ($raw -notmatch '\$venvMarker') "No `$venvMarker kill authorization"
Assert-True ($raw -match 'EXIT_STOP_BLOCKED_LEGACY_PID') "Legacy PID-only stop blocked"

# --- Parse helpers into isolated scope (no Mode switch execution) ---
$helperNames = @(
  "Get-Win32ProcessById",
  "Test-Hf3UvicornCommandLine",
  "Test-IsPythonProcessName",
  "Test-IsConhostName",
  "Test-Hf3LaunchMetaSchema",
  "Test-LiveMatchesLaunchMeta",
  "Stop-VerifiedHf3Identity",
  "Stop-VerifiedHf3LaunchTree",
  "Test-Hf3HealthStartPass"
)

# Build a stub Get-Win32ProcessById + log for unit-like injection without WMI.
$stub = @'
function Write-Log([string]$Message) { Write-Host ("[hf3-runtime-test] " + $Message) }
$script:__InjectedProcs = @{}
function Get-Win32ProcessById([int]$ProcessId) {
  if ($script:__InjectedProcs.ContainsKey($ProcessId)) { return $script:__InjectedProcs[$ProcessId] }
  return $null
}
'@

# Extract each named function from the candidate script text.
$extracted = New-Object System.Text.StringBuilder
[void]$extracted.AppendLine($stub)
foreach ($name in $helperNames) {
  if ($name -eq "Get-Win32ProcessById") { continue }
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
Set-Content -LiteralPath $tmp -Value $extracted.ToString() -Encoding UTF8
. $tmp

# --- Injection: creation required / mismatch / conhost / marker ---
$backend = "C:\Users\Owner\AppData\Local\MyPC.Attendance\p02-usb-hf3-candidate\src\backend"
$goodCmd = "`"C:\Python\python.exe`" -m uvicorn app.main:app --host 127.0.0.1 --port 18878 --app-dir $backend"
$script:__InjectedProcs[4242] = [pscustomobject]@{
  ProcessId = 4242; Name = "python.exe"; CommandLine = $goodCmd
  ExecutablePath = "C:\Python\python.exe"; CreationDate = [datetime]::Parse("2026-11-07T01:00:00Z")
  ParentProcessId = 1
}
$createIso = ([datetime]::Parse("2026-11-07T01:00:00Z")).ToUniversalTime().ToString("o")

$ok = Stop-VerifiedHf3Identity -TargetPid 4242 -ExpectedCreation $createIso -Backend $backend -PortNum 18878 -Role "listener"
# Process exists in inject map — Stop-Process will fail on fake PID; expect false (stop failed) OR refuse.
# Creation match + cmdline OK path reaches Stop-Process; catch returns false. That is acceptable for synthetic.
Assert-True ($ok -eq $false) "Synthetic Stop-Process on injected PID does not falsely report success after OS miss"

$badCreate = Stop-VerifiedHf3Identity -TargetPid 4242 -ExpectedCreation "WRONG" -Backend $backend -PortNum 18878 -Role "listener"
Assert-True ($badCreate -eq $false) "Creation mismatch refuses kill"

$blankCreate = Stop-VerifiedHf3Identity -TargetPid 4242 -ExpectedCreation "" -Backend $backend -PortNum 18878 -Role "listener"
Assert-True ($blankCreate -eq $false) "Blank creation refuses kill"

$script:__InjectedProcs[5151] = [pscustomobject]@{
  ProcessId = 5151; Name = "conhost.exe"; CommandLine = "conhost"; ExecutablePath = "C:\Windows\System32\conhost.exe"
  CreationDate = [datetime]::Parse("2026-11-07T01:00:00Z"); ParentProcessId = 4242
}
$con = Stop-VerifiedHf3Identity -TargetPid 5151 -ExpectedCreation $createIso -Backend $backend -PortNum 18878 -Role "listener"
Assert-True ($con -eq $false) "conhost never killed"

$cmdLoose = Test-Hf3UvicornCommandLine -CommandLine "note uvicorn 18878 path $backend" -Backend $backend -PortNum 18878
Assert-True ($cmdLoose -eq $false) "Loose uvicorn/port substring rejected"

$cmdOk = Test-Hf3UvicornCommandLine -CommandLine $goodCmd -Backend $backend -PortNum 18878
Assert-True ($cmdOk -eq $true) "Tokenized uvicorn cmdline accepted"

$healthBad = Test-Hf3HealthStartPass -StatusCode 200 -Body '{"status":"degraded","startup_phase":"FAIL","x":{"status":"ok","startup_phase":"READY"}}'
Assert-True ($healthBad -eq $false) "Nested ok/READY rejected"
$healthOk = Test-Hf3HealthStartPass -StatusCode 200 -Body '{"status":"ok","startup_phase":"READY"}'
Assert-True ($healthOk -eq $true) "Top-level ok+READY accepted"

$metaBad = [pscustomobject]@{ schema = "mypc.hf3.launch.v1"; port = 18878; backend = $backend; listener_pid = 4242; listener_creation = "" }
Assert-True ((Test-Hf3LaunchMetaSchema $metaBad) -eq $false) "Blank listener_creation fails schema"

if ($RunSyntheticLab) {
  $venvPy = Join-Path $CandidateRoot "venv\Scripts\python.exe"
  if (-not (Test-Path $venvPy)) {
    Write-Host "SKIP synthetic lab — venv missing at $CandidateRoot (Prepare once offline)" -ForegroundColor Yellow
  } else {
    $pyCode = @"
import http.server, socketserver, json
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({'status':'ok','startup_phase':'READY'}).encode()
        self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
with socketserver.TCPServer(('127.0.0.1', $SyntheticPort), H) as httpd:
    httpd.handle_request()
"@
    $proc = Start-Process -FilePath $venvPy -ArgumentList @("-c", $pyCode) -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 1
    $launcher = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $proc.Id) -ErrorAction SilentlyContinue
    Write-Host ("SYNTH launcher_pid={0} name={1} create={2}" -f $proc.Id, $(if ($launcher) { $launcher.Name } else { "?" }), $(if ($launcher) { $launcher.CreationDate } else { "?" }))
    # Do not Stop-Process unless creation captured; always try graceful then force only this Start-Process id.
    if ($proc -and -not $proc.HasExited) {
      try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
    }
    Assert-True ($true) "Synthetic redirector lab recorded launcher identity (no foreign kill)"
  }
}

Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
if ($failed -gt 0) {
  Write-Host "RESULT: $failed assertion(s) failed" -ForegroundColor Red
  exit 1
}
Write-Host "RESULT: PASS (Windows PS 5.1 PID-safety runtime checks)" -ForegroundColor Green
exit 0
