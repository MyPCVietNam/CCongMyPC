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
