"""HF3 18878 PID ownership decision matrix (no Windows / no sockets)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MOD_PATH = ROOT / "scripts" / "windows" / "hf3_pid_ownership.py"


def _load():
    spec = importlib.util.spec_from_file_location("hf3_pid_ownership", MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


m = _load()
P = m.ProcessSnap

BACKEND = r"C:\Users\owner\AppData\Local\MyPC.Attendance\p02-usb-hf3-candidate\src\MyPC.Attendance\backend"
CMD = (
    f'"{BACKEND}\\..\\..\\venv\\Scripts\\python.exe" -m uvicorn app.main:app '
    f'--host 127.0.0.1 --port 18878 --app-dir {BACKEND}'
)


def test_direct_launcher_owns_listener_ready_health():
    launcher = P(100, "python.exe", 1, CMD, "2026-11-07T03:00:00Z")
    procs = {100: launcher}
    rel, pid, reason = m.classify_port_listeners(
        launcher, [100], procs, port=18878, backend=BACKEND
    )
    assert rel == m.REL_DIRECT
    assert pid == 100
    assert m.health_is_start_pass(200, '{"status":"ok","startup_phase":"READY"}')


def test_verified_python_child_owns_listener():
    launcher = P(200, "python.exe", 1, "venv redirector", "2026-11-07T03:00:00Z")
    child = P(300, "python.exe", 200, CMD, "2026-11-07T03:00:01Z")
    procs = {200: launcher, 300: child}
    rel, pid, reason = m.classify_port_listeners(
        launcher, [300], procs, port=18878, backend=BACKEND
    )
    assert rel == m.REL_VERIFIED_DESCENDANT
    assert pid == 300


def test_conhost_child_never_accepted():
    launcher = P(200, "python.exe", 1, "venv", "t0")
    child = P(301, "conhost.exe", 200, "conhost", "t1")
    rel, reason = m.classify_listener_ownership(
        launcher, child, {200: launcher, 301: child}, port=18878, backend=BACKEND
    )
    assert rel == m.REL_UNVERIFIED
    assert "conhost" in reason


def test_stranger_http_200_not_owned():
    launcher = P(200, "python.exe", 1, "venv", "t0")
    stranger = P(999, "python.exe", 1, CMD, "t9")
    rel, pid, reason = m.classify_port_listeners(
        launcher, [999], {200: launcher, 999: stranger}, port=18878, backend=BACKEND
    )
    assert rel == m.REL_UNVERIFIED
    assert pid is None
    assert m.health_is_start_pass(200, '{"status":"ok","startup_phase":"READY"}')  # health alone ≠ ownership


def test_wrong_app_dir_rejected():
    launcher = P(200, "python.exe", 1, "venv", "t0")
    wrong = P(
        300,
        "python.exe",
        200,
        "-m uvicorn app.main:app --host 127.0.0.1 --port 18878 --app-dir C:\\other\\backend",
        "t1",
    )
    rel, _ = m.classify_listener_ownership(
        launcher, wrong, {200: launcher, 300: wrong}, port=18878, backend=BACKEND
    )
    assert rel == m.REL_UNVERIFIED


def test_listener_creation_before_launcher_rejected():
    launcher = P(200, "python.exe", 1, "venv", "2026-11-07T04:00:00Z")
    child = P(300, "python.exe", 200, CMD, "2026-11-07T03:00:00Z")
    rel, reason = m.classify_listener_ownership(
        launcher, child, {200: launcher, 300: child}, port=18878, backend=BACKEND
    )
    assert rel == m.REL_UNVERIFIED
    assert "creation" in reason


def test_ambiguous_multiple_listeners():
    launcher = P(200, "python.exe", 1, "venv", "t0")
    rel, pid, reason = m.classify_port_listeners(
        launcher, [300, 301], {200: launcher}, port=18878, backend=BACKEND
    )
    assert rel == m.REL_AMBIGUOUS
    assert pid is None


def test_health_fail_and_degraded_never_start_pass():
    assert not m.health_is_start_pass(200, '{"status":"ok","startup_phase":"FAIL"}')
    assert not m.health_is_start_pass(200, '{"status":"degraded","startup_phase":"READY"}')
    assert not m.health_is_start_pass(200, '{"status":"ok","startup_phase":"READY"}'.replace("ok", "degraded"))
    assert m.health_is_start_pass(200, '{"status":"ok","startup_phase":"READY"}')


def test_should_kill_requires_creation_match():
    assert m.should_kill_process(
        relationship=m.REL_VERIFIED_DESCENDANT,
        meta_listener_pid=300,
        meta_listener_creation="T1",
        live_pid=300,
        live_creation="T1",
    )
    assert not m.should_kill_process(
        relationship=m.REL_VERIFIED_DESCENDANT,
        meta_listener_pid=300,
        meta_listener_creation="T1",
        live_pid=300,
        live_creation="T_REUSED",
    )
    assert not m.should_kill_process(
        relationship=m.REL_UNVERIFIED,
        meta_listener_pid=300,
        meta_listener_creation="T1",
        live_pid=300,
        live_creation="T1",
    )


def test_grandchild_python_accepted():
    launcher = P(200, "python.exe", 1, "venv", "t0")
    mid = P(250, "python.exe", 200, "helper", "t0b")
    child = P(300, "python.exe", 250, CMD, "t1")
    procs = {200: launcher, 250: mid, 300: child}
    rel, pid, _ = m.classify_port_listeners(
        launcher, [300], procs, port=18878, backend=BACKEND
    )
    assert rel == m.REL_VERIFIED_DESCENDANT
    assert pid == 300


def test_kill_requires_creation_and_rejects_marker_only_python():
    assert not m.kill_authorized(
        role="launcher",
        expected_creation="",
        live_creation="T1",
        is_conhost=False,
        cmdline_ok=False,
        is_python=True,
        exe_matches_expected=False,
    )
    assert not m.kill_authorized(
        role="launcher",
        expected_creation="T1",
        live_creation="T1",
        is_conhost=False,
        cmdline_ok=False,
        is_python=True,
        exe_matches_expected=False,  # path substring alone is insufficient
    )
    assert m.kill_authorized(
        role="launcher",
        expected_creation="T1",
        live_creation="T1",
        is_conhost=False,
        cmdline_ok=False,
        is_python=True,
        exe_matches_expected=True,
    )
    assert m.kill_authorized(
        role="listener",
        expected_creation="T1",
        live_creation="T1",
        is_conhost=False,
        cmdline_ok=True,
        is_python=True,
        exe_matches_expected=False,
    )
    assert not m.kill_authorized(
        role="listener",
        expected_creation="T1",
        live_creation="T_REUSED",
        is_conhost=False,
        cmdline_ok=True,
        is_python=True,
        exe_matches_expected=False,
    )


def test_loose_port_substring_without_tokens_rejected():
    loose = f"something 18878 uvicorn note --app-dir {BACKEND}"
    assert not m.uvicorn_cmdline_matches(loose, port=18878, backend=BACKEND)


def test_foreign_app_dir_rejected_even_when_hf3_path_in_other_arg():
    cmd = (
        r'"C:\Python\python.exe" -m uvicorn app.main:app --host 127.0.0.1 '
        r"--port 18878 --app-dir C:\ForeignService\backend "
        f'--log-config "{BACKEND}\\logging.ini"'
    )
    assert not m.uvicorn_cmdline_matches(cmd, port=18878, backend=BACKEND)


def test_app_dir_prefix_and_wrong_port_rejected():
    assert not m.uvicorn_cmdline_matches(
        f'py -m uvicorn app.main:app --host 127.0.0.1 --port 18878 --app-dir {BACKEND}2',
        port=18878,
        backend=BACKEND,
    )
    assert not m.uvicorn_cmdline_matches(
        f'py -m uvicorn app.main:app --host 127.0.0.1 --port 188780 --app-dir {BACKEND}',
        port=18878,
        backend=BACKEND,
    )


def test_quoted_app_dir_with_spaces_accepted():
    spaced = BACKEND.replace("backend", "MyPC Attendance\\backend")
    cmd = (
        f'py -m uvicorn app.main:app --host 127.0.0.1 --port 18878 --app-dir "{spaced}"'
    )
    assert m.uvicorn_cmdline_matches(cmd, port=18878, backend=spaced)


def test_duplicate_app_dir_flags_rejected():
    cmd = (
        f'py -m uvicorn app.main:app --host 127.0.0.1 --port 18878 '
        f'--app-dir {BACKEND} --app-dir C:\\Other\\backend'
    )
    assert not m.uvicorn_cmdline_matches(cmd, port=18878, backend=BACKEND)


def test_launcher_cleanup_tri_state():
    assert m.launcher_cleanup_outcome(
        launcher_pid=0, launcher_creation="", launcher_alive=False, stop_result=None
    ) == "absent"
    assert m.launcher_cleanup_outcome(
        launcher_pid=9, launcher_creation="T", launcher_alive=False, stop_result=None
    ) == "absent"
    assert m.launcher_cleanup_outcome(
        launcher_pid=9, launcher_creation="", launcher_alive=True, stop_result=None
    ) == "incomplete"
    assert m.launcher_cleanup_outcome(
        launcher_pid=9, launcher_creation="T", launcher_alive=True, stop_result=False
    ) == "incomplete"
    assert m.launcher_cleanup_outcome(
        launcher_pid=9, launcher_creation="T", launcher_alive=True, stop_result=True
    ) == "stopped"


def test_health_requires_top_level_ok_ready_not_nested():
    nested = '{"status":"degraded","startup_phase":"FAIL","detail":{"status":"ok","startup_phase":"READY"}}'
    assert not m.health_is_start_pass(200, nested)
    assert m.health_is_start_pass(200, '{"status":"ok","startup_phase":"READY"}')
    assert not m.health_is_start_pass(200, '{"status":"ok","startup_phase":"FAIL"}')
    assert not m.health_is_start_pass(503, '{"status":"ok","startup_phase":"READY"}')


def test_conhost_never_authorized_to_kill():
    assert not m.kill_authorized(
        role="listener",
        expected_creation="T1",
        live_creation="T1",
        is_conhost=True,
        cmdline_ok=True,
        is_python=False,
        exe_matches_expected=False,
    )
