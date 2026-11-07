"""Independent fail-closed HF3 PID guards. PURE READ-ONLY Python tests.

Usage in Cursor's repository: set HF3_REPO_ROOT to the directory containing
MyPC.Attendance/, then run: python -m pytest -q <this-file>

This test file does not spawn, enumerate, or terminate any processes, open sockets,
read camera frames, access secrets, or write to HF3 candidate directories.
Tests are expected to be RED on PR #27 freeze 0ea4264440bf330f005af7447bbd6bdb6cfabb46.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import re
import sys


def repo_root():
    explicit = os.environ.get("HF3_REPO_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


ROOT = repo_root()
PKG = ROOT / "MyPC.Attendance" if (ROOT / "MyPC.Attendance").is_dir() else ROOT
SCRIPTS = PKG / "scripts" / "windows"
PS1 = (SCRIPTS / "p02_usb_hf3_candidate_18878.ps1").read_text(encoding="utf-8-sig")
HARNESS = (SCRIPTS / "p02_usb_hf3_pid_safety_runtime_tests.ps1").read_text(encoding="utf-8-sig")


def _load_pure_helper():
    p = SCRIPTS / "hf3_pid_ownership.py"
    spec = importlib.util.spec_from_file_location("hf3_pid_safety_v3_pure", p)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _between(s, start, end):
    return s.split(start, 1)[1].split(end, 1)[0]


def test_default_harness_must_not_call_real_stop_on_hardcoded_fake_pid():
    default = HARNESS.split("if ($RunSyntheticLab)", 1)[0]
    # This is a real call through a dot-sourced function that invokes Stop-Process.
    # A fake CIM process with PID 4242 does not make the real OS PID 4242 safe.
    assert not re.search(r"(?i)Stop-VerifiedHf3Identity\s+-TargetPid\s+4242\b", default), (
        "UNSAFE: default runtime harness routes synthetic PID 4242 to real Stop-Process; "
        "replace with a DI-isolated mock or pure simulation before any Windows run"
    )


def test_synthetic_lab_must_not_mark_pass_unconditionally():
    lab = HARNESS.split("if ($RunSyntheticLab)", 1)[1]
    assert not re.search(r"Assert-True\s*\(\s*\$true\s*\)", lab, re.IGNORECASE), (
        "Synthetic lab records PASS without validating child ownership or cleanup"
    )


def test_synthetic_lab_cannot_leave_blocked_handle_request_without_request():
    lab = HARNESS.split("if ($RunSyntheticLab)", 1)[1]
    # An HTTP server waiting in handle_request() needs an actual request and verified
    # teardown of the listener *and* launcher. Merely killing launcher is insufficient.
    if "httpd.handle_request()" in lab:
        assert any(x in lab for x in ["Invoke-WebRequest", "Invoke-RestMethod", "HttpClient", "urllib.request", "socket.create_connection"]), (
            "Synthetic listener blocks waiting for a request; launcher-only kill may orphan venv Python child"
        )


def test_python_command_verification_rejects_wrong_app_dir_even_if_other_arg_mentions_hf3():
    m = _load_pure_helper()
    backend = r"C:\Users\Owner\AppData\Local\MyPC.Attendance\p02-usb-hf3-candidate\src\MyPC.Attendance\backend"
    cmd = (
        r'"C:\Python\python.exe" -m uvicorn app.main:app --host 127.0.0.1 '
        r'--port 18878 --app-dir C:\ForeignService\backend --log-config "'
        + backend + r'\logging.ini"'
    )
    assert not m.uvicorn_cmdline_matches(cmd, port=18878, backend=backend), (
        "Python ownership mirror accepted a FOREIGN --app-dir due to unrelated path substring"
    )


def test_production_ps_powershell_has_no_anywhere_path_fallback_for_app_dir():
    helper = _between(PS1, "function Test-Hf3UvicornCommandLine {", "function Test-IsPythonProcessName")
    assert "$CommandLine.IndexOf($backendNorm" not in helper, (
        "Production PowerShell accepts backend path in a different argument when --app-dir is foreign"
    )


def test_stop_without_listener_cannot_ignore_failed_launcher_stop():
    stop = _between(PS1, '  "Stop" {', '  "Diagnose" {')
    no_listener = stop.split("# No listener:", 1)[1]
    assert not re.search(r"(?i)\[void\]\s*\(Stop-VerifiedHf3Identity", no_listener), (
        "Stop ignores failed launcher cleanup and can report Stop OK solely because the port is free"
    )

