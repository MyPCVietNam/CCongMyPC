# Requires Pester >= 5.9.0, Windows PowerShell 5.1.
# PURE static contract. Intentionally never dot-sources candidate or invokes Stop-Process.
BeforeAll {
    $script:repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
    $script:hf3 = Join-Path $script:repoRoot 'MyPC.Attendance\scripts\windows\p02_usb_hf3_candidate_18878.ps1'
    $script:runtime = Join-Path $script:repoRoot 'MyPC.Attendance\scripts\windows\p02_usb_hf3_pid_safety_runtime_tests.ps1'
}

Describe 'MyPC HF3 Windows process-safety contract' {
    It 'never assigns foreach loop variable to reserved $PID' {
        $raw = Get-Content -LiteralPath $script:hf3 -Raw -Encoding UTF8
        $raw | Should -Not -Match '(?i)\bforeach\s*\(\s*\$pid\b'
    }
    It 'does not fall back to substring matching for --app-dir' {
        $raw = Get-Content -LiteralPath $script:hf3 -Raw -Encoding UTF8
        $start = $raw.IndexOf('function Test-Hf3UvicornCommandLine')
        $end = $raw.IndexOf('function Test-IsPythonProcessName')
        $start | Should -BeGreaterThan -1
        $end | Should -BeGreaterThan $start
        $raw.Substring($start, $end - $start) | Should -Not -Match '(?i)\bIndexOf\s*\(\s*\$backendNorm'
    }
    It 'never sends synthetic PID 4242 to a live kill boundary' {
        $raw = Get-Content -LiteralPath $script:runtime -Raw -Encoding UTF8
        $raw | Should -Not -Match '(?i)\bStop-VerifiedHf3Identity\s+-TargetPid\s+4242\b'
    }
    It 'contains no real Stop-Process execution in synthetic runtime tests' {
        $raw = Get-Content -LiteralPath $script:runtime -Raw -Encoding UTF8
        $raw | Should -Not -Match '(?im)^\s*(?:try\s*\{\s*)?Stop-Process\b'
    }
    It 'stores both launcher and listener creation identities' {
        $raw = Get-Content -LiteralPath $script:hf3 -Raw -Encoding UTF8
        $raw | Should -Match 'launcher_creation'
        $raw | Should -Match 'listener_creation'
    }
    It 'Start free-port branch probes launch meta before cleanup' {
        $raw = Get-Content -LiteralPath $script:hf3 -Raw -Encoding UTF8
        $start = $raw.IndexOf('"Start" {')
        $stop = $raw.IndexOf('"Stop" {')
        $start | Should -BeGreaterThan -1
        $stop | Should -BeGreaterThan $start
        $branch = $raw.Substring($start, $stop - $start)
        $branch | Should -Match 'Stale metadata with free port'
        $branch | Should -Match 'Read-Hf3LaunchMeta'
        $branch | Should -Match 'Get-Win32ProcessById'
        $branch | Should -Match 'EXIT_START_STALE_LAUNCHER'
        $branch | Should -Match 'EXIT_START_STALE_IDENTITY_UNVERIFIED'
        $branch | Should -Match 'EXIT_STOP_BLOCKED_LEGACY_PID'
    }
    It 'Test-Hf3UvicornCommandLine uses contiguous -m uvicorn entrypoint walk' {
        $raw = Get-Content -LiteralPath $script:hf3 -Raw -Encoding UTF8
        $fnStart = $raw.IndexOf('function Test-Hf3UvicornCommandLine')
        $fnEnd = $raw.IndexOf('function Test-IsPythonProcessName')
        $fnStart | Should -BeGreaterThan -1
        $fnEnd | Should -BeGreaterThan $fnStart
        $helper = $raw.Substring($fnStart, $fnEnd - $fnStart)
        $helper | Should -Not -Match 'for \(\$i = 0; \$i -lt \(\$argv\.Count - 1\); \$i\+\+\)'
        $helper | Should -Match '(?i)-c'
        $helper | Should -Match 'uvicorn'
    }
    It 'DIRECT listener requires Python process name' {
        $raw = Get-Content -LiteralPath $script:hf3 -Raw -Encoding UTF8
        $raw | Should -Match 'Test-IsPythonProcessName \$listener\.Name'
    }
    It 'synthetic lab is approval-gated and never qualifies real Stop-Process' {
        $raw = Get-Content -LiteralPath $script:runtime -Raw -Encoding UTF8
        $raw | Should -Match 'MYPC_HF3_SYNTHETIC_LAB_APPROVED'
        $raw | Should -Not -Match '(?i)Microsoft\.PowerShell\.Management\\Stop-Process'
        $raw | Should -Match '(?i)function Stop-Process'
    }
}
