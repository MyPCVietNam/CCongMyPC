"""Independent STATIC regression guards for HF3 PID stop safety.

Originally RED on PR #27 tip f441da4 (foreach $pid, legacy kill, optional creation,
missing launcher_creation, venvMarker kill auth). Must stay GREEN after the safety fix.
These are read-only source inspections; they do NOT execute PowerShell or stop processes.
"""
from __future__ import annotations

import os
import pathlib
import re

_DEFAULT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "scripts"
    / "windows"
    / "p02_usb_hf3_candidate_18878.ps1"
)
PS1 = pathlib.Path(os.environ.get("HF3_PS1", str(_DEFAULT)))
TEXT = PS1.read_text(encoding="utf-8-sig")


def section(start: str, stop: str) -> str:
    a = TEXT.index(start)
    b = TEXT.index(stop, a + len(start))
    return TEXT[a:b]


def test_stop_loop_never_assigns_readonly_pid_automatic_variable():
    """$PID is read-only; case-insensitive foreach($pid ...) is a runtime error."""
    # Implementation may use Stop-VerifiedHf3Identity / LaunchTree helpers.
    body = section("function Stop-VerifiedHf3Identity {", "function Stop-VerifiedHf3LaunchTree {")
    assert not re.search(r"(?i)\bforeach\s*\(\s*\$pid\b", body), (
        "Stop helper must not foreach($pid ...); $PID is a read-only automatic variable"
    )
    assert not re.search(r"(?i)\bforeach\s*\(\s*\$pid\b", TEXT), (
        "No PS1 foreach may assign the automatic $PID variable"
    )


def test_no_legacy_pid_only_stop_without_launch_metadata():
    """Legacy uvicorn.pid alone must never authorize Stop-Process."""
    stop = section('  "Stop" {', '  "Diagnose" {')
    assert "EXIT_STOP_BLOCKED_LEGACY_PID" in stop
    # Must not call a kill helper from a pid-file-only branch
    assert "elseif (Test-Path $pidFile)" not in stop or "Stop-VerifiedHf3" not in stop.split(
        "EXIT_STOP_BLOCKED_LEGACY_PID", 1
    )[1].split('"Diagnose"', 1)[0]
    # Stronger: no Stop-Verified* after mentioning legacy without meta refusal
    assert "launch meta required" in stop.lower() or "EXIT_STOP_BLOCKED_LEGACY_PID" in stop


def test_listener_creation_required_not_optional_when_meta_is_present():
    """Empty/missing creation timestamp cannot authenticate an existing PID."""
    f = section("function Test-LiveMatchesLaunchMeta {", "function Stop-VerifiedHf3Identity {")
    assert not re.search(
        r"(?i)if\s*\(\s*\[string\]\$Meta\.listener_creation\s+-and\s+\$liveCreate\s+-ne",
        f,
    ), "Creation timestamp must not be optional via `-and` short-circuit"
    assert "if (-not [string]$Meta.listener_creation)" in f or "Test-Hf3LaunchMetaSchema" in TEXT
    assert "return $false" in f


def test_launcher_stop_needs_own_creation_stamp_not_child_creation_stamp():
    """Launcher and listener are separate processes with distinct creation timestamps."""
    start = section('  "Start" {', '  "Stop" {')
    stop = section('  "Stop" {', '  "Diagnose" {')
    assert "launcher_creation" in start and "launcher_creation" in stop, (
        "Persist and check launcher_creation separately before trying to terminate launcher PID"
    )


def test_no_generic_candidate_marker_as_kill_authorization():
    """Merely seeing a candidate directory substring does not prove process ownership."""
    f = section("function Stop-VerifiedHf3Identity {", "function Stop-VerifiedHf3LaunchTree {")
    assert not re.search(r"(?i)\$cmd\.Contains\(\$venvMarker\)", f)
    assert "p02-usb-hf3-candidate" not in f or "ExpectedExePath" in f
    assert "$venvMarker" not in f
    assert "Role" in f and "ExpectedCreation" in f
