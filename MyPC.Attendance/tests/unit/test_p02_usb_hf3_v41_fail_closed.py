"""HF3 PID Safety V4.1 residual fail-closed contracts (no OS side effects)."""
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
HARNESS = (SCRIPTS / "p02_usb_hf3_v4_fail_closed_runtime_tests.ps1").read_text(encoding="utf-8-sig")


def _fn(name: str, nxt: str) -> str:
    return PS.split(f"function {name}", 1)[1].split(f"function {nxt}", 1)[0]


def _mode(name: str, nxt: str) -> str:
    return PS.split(f'  "{name}" {{', 1)[1].split(f'  "{nxt}" {{', 1)[0]


def load_helper():
    source = SCRIPTS / "hf3_pid_ownership.py"
    spec = importlib.util.spec_from_file_location("mypc_hf3_v41", source)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_r1_start_validates_schema_before_cleanup():
    start = _mode("Start", "Stop")
    free = start.split("Stale metadata with free port", 1)[1].split("$launchNonce", 1)[0]
    assert "Validate-Hf3LaunchMetaBeforeCleanup" in free
    assert "EXIT_START_INVALID_LAUNCH_META" in free


def test_r2_update_validates_schema_before_swap():
    update = _mode("Update", "Preflight")
    free = update.split("Port free:", 1)[1].split("$backupLeaf", 1)[0]
    assert "Validate-Hf3LaunchMetaBeforeCleanup" in free
    assert "EXIT_UPDATE_INVALID_LAUNCH_META" in free


def test_r3_stop_no_listener_probes_saved_listener_pid():
    stop = _mode("Stop", "Diagnose")
    no_listener = stop.split("# No listener:", 1)[1]
    assert re.search(
        r"(?:Get-Win32ProcessById|Stop-VerifiedHf3Identity)[\s\S]{0,260}(?:listener_pid|listenerPidStop)",
        no_listener,
        re.I,
    )
    assert "EXIT_STOP_STALE_LISTENER" in no_listener


def test_r4_update_checks_legacy_pid_file():
    update = _mode("Update", "Preflight")
    free = update.split("Port free:", 1)[1].split("$backupLeaf", 1)[0]
    assert "$pidFile" in free
    assert "EXIT_UPDATE_BLOCKED_LEGACY_PID" in free or "legacy" in free.lower()


def test_r5_tcp_empty_requires_category_not_substring():
    tcp = _fn("Get-Hf3PortListenerOwnerPids", "Resolve-Hf3ListenerOwnership")
    assert "Test-Hf3TcpEmptyQueryError" in tcp
    assert not re.search(
        r"No MSFT_NetTCPConnection\|ObjectNotFound\|No matching\|cannot find",
        tcp,
        re.I,
    )
    empty = _fn("Test-Hf3TcpEmptyQueryError", "Get-Hf3PortListenerOwnerPids")
    assert "ObjectNotFound" in empty
    assert "timeout" in empty.lower()


def test_r6_python_mirror_refuses_non_python_listener():
    mod = load_helper()
    assert not mod.kill_authorized(
        role="listener",
        expected_creation="2026-11-07T10:00:00Z",
        live_creation="2026-11-07T10:00:00Z",
        is_conhost=False,
        cmdline_ok=True,
        is_python=False,
        exe_matches_expected=False,
    )
    assert not mod.kill_authorized(
        role="listener",
        expected_creation="2026-11-07T10:00:00Z",
        live_creation="2026-11-07T10:00:00Z",
        is_conhost=True,
        cmdline_ok=True,
        is_python=True,
        exe_matches_expected=True,
    )
    assert not mod.kill_authorized(
        role="listener",
        expected_creation="2026-11-07T10:00:00Z",
        live_creation="2026-11-07T11:00:00Z",
        is_conhost=False,
        cmdline_ok=True,
        is_python=True,
        exe_matches_expected=True,
    )
    assert mod.kill_authorized(
        role="listener",
        expected_creation="2026-11-07T10:00:00Z",
        live_creation="2026-11-07T10:00:00Z",
        is_conhost=False,
        cmdline_ok=True,
        is_python=True,
        exe_matches_expected=True,
    )


def test_r7_harness_covers_handler_control_flows():
    assert (
        "Stop-VerifiedHf3LaunchTree" in HARNESS
        or "Invoke-Hf3StopHandler" in HARNESS
        or "Invoke-Hf3UpdateHandler" in HARNESS
    )
    assert "Invoke-Hf3StopHandler" in HARNESS
    assert "Invoke-Hf3UpdateHandler" in HARNESS
    assert "Invoke-Hf3StartHandler" in HARNESS


def test_r8_update_decision_foreach_has_no_stop_verified():
    update = _mode("Update", "Preflight")
    free = update.split("Port free:", 1)[1].split("$backupLeaf", 1)[0]
    probe_loop = free.split("foreach ($rolePidName", 1)[1]
    assert "Stop-VerifiedHf3Identity" not in probe_loop
    assert "EXIT_UPDATE_STALE_LISTENER" in free
