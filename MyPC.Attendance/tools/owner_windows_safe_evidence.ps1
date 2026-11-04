#Requires -Version 5.1
<#
.SYNOPSIS
  Read-only, sanitized health/evidence collector for MyPC Attendance staging.

.DESCRIPTION
  Hits health endpoints only. Never reads DataDir, secrets, SQLite, embeddings, or photos.
  Writes a redacted JSON summary suitable for owner handoff.

.PARAMETER BaseUrl
  Staging API base, e.g. http://127.0.0.1:18080

.PARAMETER OutFile
  Output path for sanitized JSON (default: .\mypc-safe-evidence.json)
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,
    [string]$OutFile = ".\mypc-safe-evidence.json"
)

$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd("/")

function Get-SafeJson([string]$Url) {
    try {
        $resp = Invoke-WebRequest -Uri $Url -Method GET -UseBasicParsing -TimeoutSec 15
        $obj = $resp.Content | ConvertFrom-Json
        return @{ ok = $true; status = [int]$resp.StatusCode; body = $obj }
    }
    catch {
        return @{ ok = $false; error = $_.Exception.Message }
    }
}

function Redact-Object($obj) {
    if ($null -eq $obj) { return $null }
    if ($obj -is [string]) {
        # Strip obvious userinfo in URLs if any slipped into health payloads
        return ($obj -replace "://[^/@\s]+:[^/@\s]+@", "://***:***@")
    }
    if ($obj -is [System.Collections.IDictionary] -or $obj.PSObject.Properties) {
        $out = [ordered]@{}
        foreach ($p in $obj.PSObject.Properties) {
            $name = [string]$p.Name
            $low = $name.ToLowerInvariant()
            if ($low -match "password|passwd|secret|token|cookie|embedding|photo|private.?key") {
                $out[$name] = "[REDACTED]"
                continue
            }
            $out[$name] = Redact-Object $p.Value
        }
        return $out
    }
    if ($obj -is [System.Collections.IEnumerable] -and -not ($obj -is [string])) {
        $list = @()
        foreach ($item in $obj) { $list += ,(Redact-Object $item) }
        return $list
    }
    return $obj
}

$summary = [ordered]@{
    schema           = "mypc.owner-windows-safe-evidence.v1"
    collected_at_utc = [DateTime]::UtcNow.ToString("o")
    base_url         = $BaseUrl
    note             = "Read-only. No DataDir/secrets/SQLite/embeddings. Physical gates remain OWNER-ONLY."
    health           = Redact-Object (Get-SafeJson "$BaseUrl/health")
    gateway_health   = Redact-Object (Get-SafeJson "$BaseUrl/api/v1/gateway/health")
}

$summary | ConvertTo-Json -Depth 8 | Set-Content -Path $OutFile -Encoding UTF8
Write-Host "Wrote sanitized evidence: $OutFile"
Write-Host "Do NOT attach production DataDir, secrets, or employee media to any handoff."
