# Capture runtime pins on Windows staging. No secrets printed.
# Run from an elevated or service account shell after venv activate.
$ErrorActionPreference = 'Stop'
$out = Join-Path $PSScriptRoot '..\owner-captured'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$dest = Join-Path $out 'RUNTIME_VERSIONS_WINDOWS.txt'

@(
  "captured_at_local=$([DateTime]::Now.ToString('o'))"
  "python=$(python --version 2>&1)"
  "pip_fastapi=$(pip show fastapi | Select-String -Pattern '^(Name|Version):')"
  "pip_check=$(pip check 2>&1 | Out-String)"
  "git_head=$(git rev-parse HEAD 2>&1)"
) | Set-Content -Path $dest -Encoding utf8

Write-Host "Wrote $dest"
Write-Host "Next: call GET /api/v1/health and append alembic_ok / fastapi_supported (redact data_dir if sensitive)."
