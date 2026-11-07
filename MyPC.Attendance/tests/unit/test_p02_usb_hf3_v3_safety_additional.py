"""Owner-safe, independent V3 security regression tests (no side effects).

Invocation from repository root:
  python -m pytest -q /path/to/test_hf3_v3_safety_additional.py
  # Optionally set HF3_REPO_ROOT to a path containing MyPC.Attendance/.

Expected baseline: RED on immutable feature 97c1e9/packaging 00858e3.
Do NOT bypass test by weakening assertions; prove fixes on PS5.1 and Python.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys


def repo_root() -> Path:
    root = Path(os.environ.get("HF3_REPO_ROOT") or os.getcwd()).resolve()
    return root / "MyPC.Attendance" if (root / "MyPC.Attendance").is_dir() else root


ROOT = repo_root()
SCRIPTS = ROOT / "scripts" / "windows"
PS = (SCRIPTS / "p02_usb_hf3_candidate_18878.ps1").read_text(encoding="utf-8-sig")
HARNESS = (SCRIPTS / "p02_usb_hf3_pid_safety_runtime_tests.ps1").read_text(encoding="utf-8-sig")


def load_helper():
    source = SCRIPTS / "hf3_pid_ownership.py"
    spec = importlib.util.spec_from_file_location("mypc_hf3_pid_additional", source)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def start_no_listener_branch() -> str:
    start = PS.split('  "Start" {', 1)[1].split('  "Stop" {', 1)[0]
    return start.split("# Stale metadata with free port", 1)[1].split("$launchNonce", 1)[0]


def test_start_refuses_unverified_live_launcher_when_port_free():
    branch = start_no_listener_branch()
    # A stale launch record may represent a live redirector with a free socket.
    assert "Read-Hf3LaunchMeta" in branch and "Get-Win32ProcessById" in branch, (
        "Start deletes persisted launch evidence with port free without checking launcher PID and creation"
    )


def test_start_does_not_silently_discard_legacy_pid_when_port_free():
    branch = start_no_listener_branch()
    assert "Remove-Item $pidFile" in branch  # regression present; tighten below
    assert "EXIT_STOP_BLOCKED_LEGACY_PID" in branch or "Get-Win32ProcessById" in branch, (
        "Start erases PID-only evidence without determining whether that process is alive"
    )


def test_python_owner_check_rejects_python_dash_c_even_with_uvicorn_flags():
    m = load_helper()
    cmd = (
        r'C:\Python\python.exe -c "import time; time.sleep(60)" '
        r'-m uvicorn app.main:app --host 127.0.0.1 --port 18878 '
        r'--app-dir C:\HF3\backend'
    )
    assert not m.uvicorn_cmdline_matches(cmd, port=18878, backend=r"C:\HF3\backend"), (
        "A foreign Python -c process with fake uvicorn flags is accepted as owned"
    )


def test_powershell_owner_check_requires_module_as_interpreter_entrypoint():
    helper = PS.split("function Test-Hf3UvicornCommandLine {", 1)[1].split("function Test-IsPythonProcessName", 1)[0]
    assert 'for ($i = 0; $i -lt ($argv.Count - 1); $i++)' not in helper, (
        "PowerShell permits -m uvicorn anywhere, including arguments to python -c"
    )


def test_powershell_direct_listener_requires_python_identity():
    block = PS.split("function Resolve-Hf3ListenerOwnership {", 1)[1].split("function Test-Hf3HealthStartPass", 1)[0]
    direct = block.split('if ($listenerPid -eq $LauncherPid)', 1)[1].split('if (-not (Test-IsPythonProcessName', 1)[0]
    assert 'Test-IsPythonProcessName $listener.Name' in direct, (
        "DIRECT listener is accepted without a Python process-name check (Python mirror rejects it)"
    )


def test_opt_in_synthetic_lab_does_not_kill_by_port_owner_only():
    lab = HARNESS.split("if ($RunSyntheticLab)", 1)[1]
    if "Microsoft.PowerShell.Management\\Stop-Process" in lab:
        assert 'CreationDate' in lab and 'CommandLine' in lab, (
            "Opt-in synthetic lab directly kills a PID selected by its socket without verifying creation + process identity"
        )
