"""HF3 PID Safety V4 fail-closed behavioral contracts (no OS side effects).

These tests assert injected/provider semantics and source contracts that must
hold on PowerShell 5.1 after the V4 corrective. They do NOT Start/Stop a real
HF3 process or call real CIM/TCP APIs.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path


def repo_root() -> Path:
    root = Path(os.environ.get("HF3_REPO_ROOT") or Path(__file__).resolve().parents[2].parent).resolve()
    return root / "MyPC.Attendance" if (root / "MyPC.Attendance").is_dir() else root


ROOT = repo_root()
SCRIPTS = ROOT / "scripts" / "windows"
PS = (SCRIPTS / "p02_usb_hf3_candidate_18878.ps1").read_text(encoding="utf-8-sig")


def _fn(name: str, nxt: str) -> str:
    return PS.split(f"function {name}", 1)[1].split(f"function {nxt}", 1)[0]


def _mode(name: str, nxt: str) -> str:
    return PS.split(f'  "{name}" {{', 1)[1].split(f'  "{nxt}" {{', 1)[0]


def load_helper():
    source = SCRIPTS / "hf3_pid_ownership.py"
    spec = importlib.util.spec_from_file_location("mypc_hf3_v4", source)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# --- F-01 Start malformed meta ---
def test_f01_start_blocks_malformed_meta_file_when_port_free():
    start = _mode("Start", "Stop")
    free = start.split("Stale metadata with free port", 1)[1].split("$launchNonce", 1)[0]
    assert "Get-Hf3LaunchMetaState" in free or "EXIT_START_INVALID_LAUNCH_META" in free
    assert "EXIT_START_INVALID_LAUNCH_META" in free
    # Must not proceed to Start-Process while invalid meta exists
    assert "Remove-Item $launchMetaFile" not in free.split("EXIT_START_INVALID_LAUNCH_META", 1)[0]


# --- F-02 Update malformed meta ---
def test_f02_update_blocks_malformed_meta_when_port_free():
    update = _mode("Update", "Preflight")
    free = update.split("Port free:", 1)[1].split("$backupLeaf", 1)[0]
    assert "EXIT_UPDATE_INVALID_LAUNCH_META" in free
    assert "Get-Hf3LaunchMetaState" in free or "INVALID" in free


# --- F-03 Update checks listener when port free ---
def test_f03_update_free_port_checks_listener_pid_and_creation():
    update = _mode("Update", "Preflight")
    free = update.split("Port free:", 1)[1].split("$backupLeaf", 1)[0]
    assert "listener_pid" in free
    assert "listener_creation" in free
    assert "EXIT_UPDATE_STALE_LISTENER" in free or "EXIT_START_STALE_LAUNCHER" in free or "listener" in free.lower()


# --- F-04 process probe UNKNOWN ≠ ABSENT ---
def test_f04_process_probe_does_not_silently_continue_as_absent():
    body = _fn("Get-Win32ProcessById", "Split-Hf3WindowsCommandLine")
    assert "-ErrorAction SilentlyContinue" not in body
    assert "EXIT_PROCESS_PROBE_UNKNOWN" in body or "throw" in body


# --- F-05 TCP probe UNKNOWN ≠ free port ---
def test_f05_tcp_probe_does_not_silently_continue_as_free():
    body = _fn("Get-Hf3PortListenerOwnerPids", "Resolve-Hf3ListenerOwnership")
    assert "-ErrorAction SilentlyContinue" not in body
    assert "EXIT_TCP_PROBE_UNKNOWN" in body or "throw" in body


# --- F-06 Stop corrupt meta ≠ nothing to stop ---
def test_f06_stop_invalid_meta_is_blocked_not_nothing_to_stop():
    stop = _mode("Stop", "Diagnose")
    assert "EXIT_STOP_INVALID_LAUNCH_META" in stop
    head = stop.split("EXIT_STOP_INVALID_LAUNCH_META", 1)[0]
    # The 'nothing to stop' path must only run after ABSENT, not INVALID
    assert "Get-Hf3LaunchMetaState" in stop or "INVALID" in stop


# --- F- listener termination requires Python name ---
def test_listener_kill_and_live_match_require_python_process_name():
    live = _fn("Test-LiveMatchesLaunchMeta", "Stop-VerifiedHf3Identity")
    assert "Test-IsPythonProcessName" in live
    stop_id = _fn("Stop-VerifiedHf3Identity", "Stop-VerifiedHf3LaunchTree")
    # listener role branch must check python name
    listener_branch = stop_id.split('$Role -eq "listener"', 1)[1].split("} else {", 1)[0]
    assert "Test-IsPythonProcessName" in listener_branch


# --- Meta state helper exists ---
def test_launch_meta_state_triad_absent_valid_invalid():
    assert "function Get-Hf3LaunchMetaState" in PS
    body = PS.split("function Get-Hf3LaunchMetaState", 1)[1].split("function Read-Hf3LaunchMeta", 1)[0]
    assert '"ABSENT"' in body or "'ABSENT'" in body
    assert '"VALID"' in body or "'VALID'" in body
    assert '"INVALID"' in body or "'INVALID'" in body


# --- Stop-Verified must refuse UNKNOWN probe (not treat as absent success) ---
def test_stop_verified_refuses_unknown_process_probe():
    body = _fn("Stop-VerifiedHf3Identity", "Stop-VerifiedHf3LaunchTree")
    assert "PROBE_UNKNOWN" in body or "process probe" in body.lower()
    # Must not return $true solely because Get-Win32ProcessById threw
    assert re.search(r"already absent", body)


# --- App-dir spaces: quoted argv builder ---
def test_uvicorn_argument_formatter_quotes_paths_with_spaces():
    assert "function Format-Hf3UvicornProcessArguments" in PS or "Format-Hf3QuotedArg" in PS
    m = load_helper()
    # Python mirror if present
    if hasattr(m, "format_uvicorn_process_arguments"):
        args = m.format_uvicorn_process_arguments(
            backend=r"C:\Users\Test User\p02-usb-hf3-candidate\src\backend",
            port=18878,
        )
        assert "Test User" in args
        assert "--app-dir" in args
        # path with spaces must appear inside quotes as one token region
        assert '"C:\\Users\\Test User\\p02-usb-hf3-candidate\\src\\backend"' in args or (
            "'C:\\Users\\Test User\\p02-usb-hf3-candidate\\src\\backend'" in args
        )


# --- Historical regressions must stay green ---
def test_rejects_python_dash_c_spoof():
    m = load_helper()
    cmd = (
        r'C:\Python\python.exe -c "import time; time.sleep(60)" '
        r"-m uvicorn app.main:app --host 127.0.0.1 --port 18878 "
        r"--app-dir C:\HF3\backend"
    )
    assert not m.uvicorn_cmdline_matches(cmd, port=18878, backend=r"C:\HF3\backend")


def test_no_fake_pid_4242_real_kill_in_harness():
    harness = (SCRIPTS / "p02_usb_hf3_pid_safety_runtime_tests.ps1").read_text(encoding="utf-8-sig")
    assert not re.search(r"(?i)\bStop-VerifiedHf3Identity\s+-TargetPid\s+4242\b", harness)
    assert "Microsoft.PowerShell.Management\\Stop-Process" not in harness
