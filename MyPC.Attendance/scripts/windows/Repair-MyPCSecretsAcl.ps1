﻿# MyPC Attendance - scoped existing-secret ACL recovery for Windows PowerShell 5.1
# Preserves secret content, SQLite, and camera credentials. No recursive ACL reset.
# This is a temporary Windows operator recovery, not a source-code hotfix.
param(
    [switch]$CheckOnly,
    [switch]$Repair
)

$ErrorActionPreference = 'Stop'
if ($CheckOnly -and $Repair) { throw 'Choose -CheckOnly OR -Repair.' }
if (-not $Repair) { $CheckOnly = $true }

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$expected = "$env:COMPUTERNAME\MyPC"
if ($identity.Name -ine $expected) {
    throw "Wrong Windows account. Current=$($identity.Name), expected=$expected."
}

$home = Join-Path $env:LOCALAPPDATA 'MyPC\Attendance'
$dataDir = Join-Path $home 'data'
$secretDir = Join-Path $dataDir 'secrets'
$backupRoot = Join-Path $home 'backups'
$critical = @('session.secret', 'master.key', 'face_templates.key')

function CanReadFile([string]$Path) {
    try {
        $stream = [System.IO.File]::Open(
            $Path, [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        try { $null = $stream.ReadByte(); return $true }
        finally { $stream.Dispose() }
    }
    catch { return $false }
}

# All operations require the Attendance server to be stopped.
$listener = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if ($listener) { throw 'Port 8765 is still listening. Stop MyPC Attendance before continuing.' }

if (-not (Test-Path -LiteralPath $secretDir -PathType Container)) {
    throw 'Missing secrets folder. Do NOT create new keys or a new database.'
}
$dirItem = Get-Item -LiteralPath $secretDir -Force
if (($dirItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'Secrets directory is a reparse point. Refusing to modify it.'
}

foreach ($name in $critical) {
    $live = Join-Path $secretDir $name
    if (-not (Test-Path -LiteralPath $live -PathType Leaf)) {
        throw "Missing critical secret: $name. Stop; do not regenerate."
    }
    $item = Get-Item -LiteralPath $live -Force
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or $item.Length -eq 0) {
        throw "Unexpected critical secret object: $name. Stop."
    }
    if ($name -eq 'face_templates.key' -and $item.Length -ne 32) {
        throw 'face_templates.key is not 32 bytes. Stop.'
    }
}

# Look for a readable, previous, complete backup from the earlier camera-HF upgrade.
if (-not (Test-Path -LiteralPath $backupRoot -PathType Container)) {
    throw 'Backup directory is absent. Stop.'
}
$backup = $null
$backupFolders = @(Get-ChildItem -LiteralPath $backupRoot -Directory -Filter 'pre-camera-hf-*' |
    Sort-Object LastWriteTime -Descending)
foreach ($folder in $backupFolders) {
    $isUsable = $true
    foreach ($name in $critical) {
        $p = Join-Path (Join-Path $folder.FullName 'data\secrets') $name
        if (-not (Test-Path -LiteralPath $p -PathType Leaf) -or -not (CanReadFile $p)) {
            $isUsable = $false
            break
        }
    }
    if ($isUsable) { $backup = $folder; break }
}
if (-not $backup) {
    throw 'No readable, complete pre-camera-hf backup found for the three critical secrets. Stop.'
}
Write-Host 'CRITICAL_PRESTART_BACKUP: FOUND_AND_READABLE' -ForegroundColor Green
Write-Host "WINDOWS_IDENTITY: $($identity.Name)"

$files = @(Get-ChildItem -LiteralPath $secretDir -Force -File -ErrorAction Stop)
if ($files.Count -eq 0) { throw 'Secrets folder has no files. Stop.' }
$targetFiles = @()
$unknown = @()
foreach ($file in $files) {
    if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Reparse point in secrets: $($file.Name). Stop."
    }
    if ($file.Name -match '^(session\.secret|master\.key|face_templates\.key|camera-[0-9]+\.bin)$') {
        $targetFiles += $file
    } else {
        $unknown += $file.Name
    }
}
if ($unknown.Count -gt 0) {
    Write-Host ('UNRECOGNIZED_FILES_SKIPPED: ' + ($unknown -join ', ')) -ForegroundColor Yellow
}

$unreadable = @()
foreach ($file in $targetFiles) {
    if (CanReadFile $file.FullName) {
        Write-Host ("READ PASS  " + $file.Name) -ForegroundColor Green
    } else {
        Write-Host ("READ DENIED  " + $file.Name) -ForegroundColor Yellow
        $unreadable += $file
    }
}

function CompareCriticalWithBackup() {
    foreach ($name in $critical) {
        $livePath = Join-Path $secretDir $name
        if (-not (CanReadFile $livePath)) {
            Write-Host "CHECKSUM_SKIPPED_UNREADABLE: $name" -ForegroundColor Yellow
            continue
        }
        $backupPath = Join-Path (Join-Path $backup.FullName 'data\secrets') $name
        $liveHash = (Get-FileHash -LiteralPath $livePath -Algorithm SHA256).Hash
        $backupHash = (Get-FileHash -LiteralPath $backupPath -Algorithm SHA256).Hash
        if ($liveHash -cne $backupHash) {
            throw "Critical secret differs from pre-start backup: $name. Do not overwrite or reset any key."
        }
        Write-Host "CONTENT_MATCHES_BACKUP: $name" -ForegroundColor Green
    }
}

if ($CheckOnly) {
    CompareCriticalWithBackup
    Write-Host ("CHECK_ONLY: $($unreadable.Count) unreadable of $($targetFiles.Count) recognized secret files. No changes made.")
    exit 0
}

$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run -Repair in an elevated Windows PowerShell under the SAME MyPC account.'
}
if ($unreadable.Count -eq 0) {
    CompareCriticalWithBackup
    Write-Host 'REPAIR_NOT_NEEDED: ALL_READABLE' -ForegroundColor Green
    exit 0
}

Write-Host 'This changes ACLs only on unreadable, recognized existing files inside data\secrets.'
Write-Host 'It does not reset inheritance, touch secret content, or grant rights to Everyone.'
$confirm = Read-Host 'Type REPAIR-EXISTING-SECRETS to authorize scoped ACL changes'
if ($confirm -cne 'REPAIR-EXISTING-SECRETS') { throw 'Cancelled. No ACL changes made.' }

$aclDir = Join-Path $backupRoot ('secrets-acl-before-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $aclDir -Force | Out-Null
$grant = '*' + $identity.User.Value + ':(M)'
foreach ($file in $unreadable) {
    # Capture ACL before modification; bail out if it cannot be recorded.
    $aclFile = Join-Path $aclDir ($file.Name + '.acl.txt')
    & icacls.exe $file.FullName /save $aclFile | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Cannot save original ACL: $($file.Name). Stop." }

    & icacls.exe $file.FullName /grant $grant | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Cannot grant access to $($file.Name). Stop; do not recursively reset or take ownership automatically."
    }
    if (-not (CanReadFile $file.FullName)) {
        throw "File still unreadable after ACL grant: $($file.Name). Stop."
    }
    Write-Host ("SCOPED_ACL_REPAIR: PASS  " + $file.Name) -ForegroundColor Green
}

# This compares hashes silently: do not print plaintext or SHA256 of secrets.
CompareCriticalWithBackup
foreach ($file in $targetFiles) {
    if (-not (CanReadFile $file.FullName)) {
        throw "Post-repair read check failed: $($file.Name)."
    }
}


# After scoped file grants, ensure secrets directory has inheritable ACE for current user.
# Does NOT recursively /T reset. Does NOT rewrite secret bytes.
$dirGrantUser = '*' + $identity.User.Value + ':(OI)(CI)(M)'
$dirGrantSystem = '*S-1-5-18:(OI)(CI)(F)'
& icacls.exe $secretDir /inheritance:r | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cannot set secrets directory inheritance.' }
& icacls.exe $secretDir /grant:r $dirGrantSystem | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cannot grant SYSTEM on secrets directory.' }
& icacls.exe $secretDir /grant:r $dirGrantUser | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cannot grant inheritable user ACE on secrets directory.' }
Write-Host 'DIRECTORY_INHERITABLE_ACL: PASS' -ForegroundColor Green
Write-Host 'Source-code ACL policy is fixed in PR secret-acl HF; keep using same -DataDir.' -ForegroundColor Cyan

Write-Host 'EXISTING_SECRETS_RECOVERY: PASS' -ForegroundColor Green
Write-Host 'Close elevated PowerShell, run -CheckOnly as normal MyPC, then try the app.'
Write-Host 'The source-code ACL inheritance bug is NOT fixed by this temporary recovery.' -ForegroundColor Yellow
