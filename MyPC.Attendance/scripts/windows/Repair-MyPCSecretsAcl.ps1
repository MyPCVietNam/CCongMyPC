# MyPC Attendance - scoped existing-secret ACL recovery for Windows PowerShell 5.1
# Preserves secret content, SQLite, and camera credentials. No recursive ACL reset.
# NOTE: Never assign to $HOME / $home — PowerShell automatic variable (read-only).
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

# Must NOT use $home — conflicts with automatic $HOME (case-insensitive).
$attendanceHome = Join-Path $env:LOCALAPPDATA 'MyPC\Attendance'
$dataDir = Join-Path $attendanceHome 'data'
$secretDir = Join-Path $dataDir 'secrets'
$backupRoot = Join-Path $attendanceHome 'backups'
$critical = @('session.secret', 'master.key', 'face_templates.key')
$userSid = $identity.User.Value

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

function Get-AclSidStrings([string]$Path) {
    # Resolve every ACE identity into a SID string — independent of icacls display form.
    $sec = Get-Acl -LiteralPath $Path
    $out = @()
    foreach ($rule in $sec.Access) {
        try {
            $sid = $rule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
        }
        catch {
            $sid = [string]$rule.IdentityReference
        }
        $out += [pscustomobject]@{
            Sid            = $sid
            Rights         = [string]$rule.FileSystemRights
            Inheritance    = [string]$rule.InheritanceFlags
            Propagation    = [string]$rule.PropagationFlags
            AccessControl  = [string]$rule.AccessControlType
            IsInherited    = [bool]$rule.IsInherited
        }
    }
    return $out
}

function Test-DirectoryPolicyHealthy([string]$Path, [string]$ExpectedUserSid) {
    $aces = @(Get-AclSidStrings $Path)
    $userOk = $false
    $systemOk = $false
    foreach ($ace in $aces) {
        if ($ace.AccessControl -ne 'Allow') { continue }
        $inh = $ace.Inheritance
        $hasOI = $inh -match 'ObjectInherit'
        $hasCI = $inh -match 'ContainerInherit'
        if (-not ($hasOI -and $hasCI)) { continue }
        $rights = $ace.Rights
        $modifyOrBetter = ($rights -match 'Modify|FullControl|Write|ReadAndExecute|Delete') -or ($rights -match '268435456|2032127|1245631')
        if ($ace.Sid -eq $ExpectedUserSid -and $modifyOrBetter) { $userOk = $true }
        if ($ace.Sid -eq 'S-1-5-18' -and $modifyOrBetter) { $systemOk = $true }
    }
    return ($userOk -and $systemOk)
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

# Look for a readable, previous, complete backup of the three critical secrets.
if (-not (Test-Path -LiteralPath $backupRoot -PathType Container)) {
    throw 'Backup directory is absent. Stop.'
}
$backup = $null
$backupFolders = @(Get-ChildItem -LiteralPath $backupRoot -Directory |
    Where-Object { $_.Name -match '^(pre-camera-hf-|pre-secrets-acl-|secrets-content-)' } |
    Sort-Object LastWriteTime -Descending)
foreach ($folder in $backupFolders) {
    $isUsable = $true
    foreach ($name in $critical) {
        $candidates = @(
            (Join-Path (Join-Path $folder.FullName 'data\secrets') $name),
            (Join-Path (Join-Path $folder.FullName 'secrets') $name),
            (Join-Path $folder.FullName $name)
        )
        $found = $false
        foreach ($p in $candidates) {
            if ((Test-Path -LiteralPath $p -PathType Leaf) -and (CanReadFile $p)) {
                $found = $true
                break
            }
        }
        if (-not $found) { $isUsable = $false; break }
    }
    if ($isUsable) { $backup = $folder; break }
}
if (-not $backup) {
    throw 'No readable, complete critical-secret backup found. Stop; do not regenerate keys.'
}
Write-Host 'CRITICAL_PRESTART_BACKUP: FOUND_AND_READABLE' -ForegroundColor Green
Write-Host "WINDOWS_IDENTITY: $($identity.Name)"
Write-Host "USER_SID: $userSid"
Write-Host "ATTENDANCE_HOME: $attendanceHome"

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

$dirHealthy = Test-DirectoryPolicyHealthy $secretDir $userSid
if ($dirHealthy) {
    Write-Host 'DIRECTORY_POLICY: HEALTHY (SID+(OI)(CI) via Get-Acl Translate)' -ForegroundColor Green
} else {
    Write-Host 'DIRECTORY_POLICY: NEEDS_REPAIR' -ForegroundColor Yellow
}

function Resolve-BackupSecretPath([string]$Name) {
    $candidates = @(
        (Join-Path (Join-Path $backup.FullName 'data\secrets') $Name),
        (Join-Path (Join-Path $backup.FullName 'secrets') $Name),
        (Join-Path $backup.FullName $Name)
    )
    foreach ($p in $candidates) {
        if (Test-Path -LiteralPath $p -PathType Leaf) { return $p }
    }
    return $null
}

function CompareCriticalWithBackup() {
    foreach ($name in $critical) {
        $livePath = Join-Path $secretDir $name
        if (-not (CanReadFile $livePath)) {
            Write-Host "CHECKSUM_SKIPPED_UNREADABLE: $name" -ForegroundColor Yellow
            continue
        }
        $backupPath = Resolve-BackupSecretPath $name
        if (-not $backupPath) { throw "Backup path missing for $name" }
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
    Write-Host ("CHECK_ONLY_DIR_POLICY_HEALTHY: $dirHealthy")
    exit 0
}

$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run -Repair in an elevated Windows PowerShell under the SAME MyPC account.'
}
if ($unreadable.Count -eq 0 -and $dirHealthy) {
    CompareCriticalWithBackup
    Write-Host 'REPAIR_NOT_NEEDED: ALL_READABLE_AND_DIR_HEALTHY' -ForegroundColor Green
    Write-Host 'IDEMPOTENT: no ACL mutations performed.' -ForegroundColor Cyan
    exit 0
}

Write-Host 'This changes ACLs only on unreadable, recognized existing files / unhealthy secrets directory.'
Write-Host 'It does not touch secret content, SQLite, or grant rights to Everyone.'
$confirm = Read-Host 'Type REPAIR-EXISTING-SECRETS to authorize scoped ACL changes'
if ($confirm -cne 'REPAIR-EXISTING-SECRETS') { throw 'Cancelled. No ACL changes made.' }

$aclDir = Join-Path $backupRoot ('secrets-acl-before-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $aclDir -Force | Out-Null

# Preserve directory ACL before any mutation.
$dirAclSave = Join-Path $aclDir 'secrets-dir.acl.txt'
& icacls.exe $secretDir /save $dirAclSave | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cannot save original secrets-directory ACL. Stop.' }

$grant = '*' + $userSid + ':(M)'
foreach ($file in $unreadable) {
    $aclFile = Join-Path $aclDir ($file.Name + '.acl.txt')
    & icacls.exe $file.FullName /save $aclFile | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Cannot save original ACL: $($file.Name). Stop." }

    & icacls.exe $file.FullName /grant:r $grant | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Cannot grant access to $($file.Name). Stop; do not recursively reset or take ownership automatically."
    }
    & icacls.exe $file.FullName /grant:r '*S-1-5-18:(F)' | Out-Null
    & icacls.exe $file.FullName /remove:g 'Everyone' 2>$null | Out-Null
    & icacls.exe $file.FullName /remove:g '*S-1-1-0' 2>$null | Out-Null
    if (-not (CanReadFile $file.FullName)) {
        throw "File still unreadable after ACL grant: $($file.Name). Stop."
    }
    Write-Host ("SCOPED_ACL_REPAIR: PASS  " + $file.Name) -ForegroundColor Green
}

# Compare hashes silently: do not print plaintext or SHA256 of secrets.
CompareCriticalWithBackup
foreach ($file in $targetFiles) {
    if (-not (CanReadFile $file.FullName)) {
        throw "Post-repair read check failed: $($file.Name)."
    }
}

# Ensure secrets directory has inheritable ACE — skip if already healthy (idempotent).
if (-not (Test-DirectoryPolicyHealthy $secretDir $userSid)) {
    $dirGrantUser = '*' + $userSid + ':(OI)(CI)(M)'
    $dirGrantSystem = '*S-1-5-18:(OI)(CI)(F)'
    & icacls.exe $secretDir /inheritance:r | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot set secrets directory inheritance.' }
    & icacls.exe $secretDir /grant:r $dirGrantSystem | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot grant SYSTEM on secrets directory.' }
    & icacls.exe $secretDir /grant:r $dirGrantUser | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot grant inheritable user ACE on secrets directory.' }
    & icacls.exe $secretDir /remove:g 'Everyone' 2>$null | Out-Null
    & icacls.exe $secretDir /remove:g '*S-1-1-0' 2>$null | Out-Null
    if (-not (Test-DirectoryPolicyHealthy $secretDir $userSid)) {
        throw 'Post-repair directory policy still unhealthy (SID+(OI)(CI) check failed).'
    }
    Write-Host 'DIRECTORY_INHERITABLE_ACL: APPLIED' -ForegroundColor Green
} else {
    Write-Host 'DIRECTORY_INHERITABLE_ACL: UNCHANGED (already healthy)' -ForegroundColor Cyan
}

Write-Host 'EXISTING_SECRETS_RECOVERY: PASS' -ForegroundColor Green
Write-Host 'Close elevated PowerShell, run -CheckOnly as normal MyPC, then try the app.'
Write-Host 'Keep the same -DataDir. Never regenerate keys or grant Everyone.' -ForegroundColor Cyan
