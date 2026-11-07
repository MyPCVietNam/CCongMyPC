# MyPC HF3 PID ownership investigation. No HF3 Start/Stop/Prepare or camera capture.
# Produces only process metadata and Boolean argv markers; no raw command lines.
$ErrorActionPreference = 'Stop'
$port = 18878
$root = Join-Path $env:LOCALAPPDATA 'MyPC.Attendance\p02-usb-hf3-candidate'
$venvPy = Join-Path $root 'venv\Scripts\python.exe'
Write-Host '=== HF3 CURRENT LISTENER (READ ONLY) ==='
$ls = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
if ($ls.Count -eq 0) { Write-Host 'LISTENERS=0' }
foreach ($item in $ls) {
    $ownerId = [int]$item.OwningProcess
    $owner = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $ownerId) -ErrorAction SilentlyContinue
    $parent = $null
    if ($owner) {
        $parent = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f [int]$owner.ParentProcessId) -ErrorAction SilentlyContinue
    }
    $cmd = if ($owner) { [string]$owner.CommandLine } else { '' }
    $pcmd = if ($parent) { [string]$parent.CommandLine } else { '' }
    [pscustomobject]@{
        LocalAddress = $item.LocalAddress
        ListeningPid = $ownerId
        OwnerName = if ($owner) { $owner.Name } else { 'NOT_FOUND' }
        OwnerParentPid = if ($owner) { [int]$owner.ParentProcessId } else { $null }
        ParentName = if ($parent) { $parent.Name } else { 'NOT_FOUND' }
        UvicornFlag = $cmd.Contains('uvicorn')
        AppMainFlag = $cmd.Contains('app.main:app')
        Port18878Flag = $cmd.Contains('18878')
        CandidatePathFlag = $cmd.Contains('p02-usb-hf3-candidate')
        ParentCandidateFlag = $pcmd.Contains('p02-usb-hf3-candidate')
        OwnerStarted = if ($owner) { $owner.CreationDate } else { $null }
    } | Format-List
}
Write-Host '=== PYTHON 3.12 VENV REDIRECTOR PROBE (NO NETWORK) ==='
if (-not (Test-Path $venvPy)) { throw 'HF3 venv Python missing' }
# Only sleeps for six seconds. Does not import the attendance app or bind any port.
$probe = Start-Process -FilePath $venvPy -ArgumentList '-c "import time; time.sleep(6)"' -PassThru -WindowStyle Hidden
Start-Sleep -Milliseconds 850
$children = @(Get-CimInstance Win32_Process -Filter ("ParentProcessId={0}" -f $probe.Id) -ErrorAction SilentlyContinue)
[pscustomobject]@{
    LauncherPid = $probe.Id
    LauncherName = $probe.ProcessName
    DirectChildCount = $children.Count
    ChildPid = @( $children | ForEach-Object { [int]$_.ProcessId } ) -join ','
    ChildName = @( $children | ForEach-Object { $_.Name } ) -join ','
    RedirectorChildObserved = ($children.Count -gt 0)
} | Format-List
$null = $probe.WaitForExit(8000)
Write-Host 'PID_PROBE_DONE: no process was stopped and no candidate files were changed.'
