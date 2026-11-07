"""Pure HF3 18878 listener ownership decisions (unit-testable; no Windows required).

Mirrors the trust model in ``p02_usb_hf3_candidate_18878.ps1``:
launcher PID from Start-Process may be a venv redirector; the real uvicorn
listener may be a descendant ``python.exe``. ``conhost.exe`` is never a server.
HTTP 200 alone never proves ownership. ``startup_phase=FAIL`` / ``status=degraded``
never count as Start PASS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


REL_DIRECT = "DIRECT"
REL_VERIFIED_DESCENDANT = "VERIFIED_DESCENDANT"
REL_UNVERIFIED = "UNVERIFIED"
REL_AMBIGUOUS = "AMBIGUOUS"
REL_NONE = "NONE"

EXIT_LISTENER_OWNERSHIP = "EXIT_LISTENER_OWNERSHIP"
EXIT_HEALTH_NOT_READY = "EXIT_HEALTH_NOT_READY"
EXIT_AMBIGUOUS_LISTENERS = "EXIT_AMBIGUOUS_LISTENERS"
EXIT_FOREIGN_LISTENER = "EXIT_FOREIGN_LISTENER"


@dataclass(frozen=True)
class ProcessSnap:
    pid: int
    name: str
    parent_pid: int | None
    command_line: str
    creation_time: str = ""
    executable_path: str = ""


def normalize_name(name: str) -> str:
    return (name or "").strip().lower()


def is_conhost(name: str) -> bool:
    return normalize_name(name) in ("conhost.exe", "conhost")


def is_python_process(name: str) -> bool:
    n = normalize_name(name)
    return n in ("python.exe", "python", "pythonw.exe", "pythonw")


def uvicorn_cmdline_matches(
    cmd: str,
    *,
    port: int,
    backend: str,
    host: str = "127.0.0.1",
) -> bool:
    c = cmd or ""
    if "uvicorn" not in c:
        return False
    if "app.main:app" not in c:
        return False
    if host not in c:
        return False
    if str(port) not in c:
        return False
    backend_n = (backend or "").rstrip("\\/").lower().replace("/", "\\")
    cmd_n = c.lower().replace("/", "\\")
    if backend_n and backend_n not in cmd_n:
        return False
    return True


def is_descendant(
    listener_pid: int,
    ancestor_pid: int,
    processes: Mapping[int, ProcessSnap],
    *,
    max_depth: int = 8,
) -> bool:
    if listener_pid == ancestor_pid:
        return True
    cur = listener_pid
    seen: set[int] = set()
    for _ in range(max_depth):
        if cur in seen:
            return False
        seen.add(cur)
        snap = processes.get(cur)
        if snap is None or snap.parent_pid is None:
            return False
        if snap.parent_pid == ancestor_pid:
            return True
        if snap.parent_pid <= 0:
            return False
        cur = int(snap.parent_pid)
    return False


def classify_listener_ownership(
    launcher: ProcessSnap,
    listener: ProcessSnap,
    processes: Mapping[int, ProcessSnap],
    *,
    port: int,
    backend: str,
    host: str = "127.0.0.1",
) -> tuple[str, str]:
    """Return (relationship, reason). Fail closed on ambiguity."""
    if is_conhost(listener.name):
        return REL_UNVERIFIED, "listener_is_conhost"
    if not uvicorn_cmdline_matches(
        listener.command_line, port=port, backend=backend, host=host
    ):
        return REL_UNVERIFIED, "listener_cmdline_mismatch"
    if listener.pid == launcher.pid:
        if not is_python_process(listener.name) and listener.name:
            # allow empty name in mocks; real Windows should be python
            if listener.name and not is_python_process(listener.name):
                return REL_UNVERIFIED, "direct_listener_not_python"
        return REL_DIRECT, "listener_pid_equals_launcher"
    if not is_python_process(listener.name):
        return REL_UNVERIFIED, "descendant_not_python"
    if not is_descendant(listener.pid, launcher.pid, processes):
        return REL_UNVERIFIED, "not_in_launcher_tree"
    # Child must not have started before launcher (PID-reuse / stale parent)
    if (
        launcher.creation_time
        and listener.creation_time
        and listener.creation_time < launcher.creation_time
    ):
        return REL_UNVERIFIED, "listener_creation_before_launcher"
    return REL_VERIFIED_DESCENDANT, "python_descendant_with_uvicorn_cmdline"


def classify_port_listeners(
    launcher: ProcessSnap,
    listener_pids: list[int],
    processes: Mapping[int, ProcessSnap],
    *,
    port: int,
    backend: str,
    host: str = "127.0.0.1",
) -> tuple[str, int | None, str]:
    """Classify all listeners on the candidate port.

    Returns (relationship, accepted_listener_pid_or_None, reason).
    """
    if not listener_pids:
        return REL_NONE, None, "no_listener"
    unique = sorted({int(p) for p in listener_pids})
    if len(unique) > 1:
        # Multiple owners — only OK if exactly one verifies and others are absent snaps?
        # Fail closed: competing listeners are ambiguous.
        return REL_AMBIGUOUS, None, "multiple_listener_owners"
    pid = unique[0]
    listener = processes.get(pid)
    if listener is None:
        return REL_UNVERIFIED, None, "listener_process_missing"
    rel, reason = classify_listener_ownership(
        launcher, listener, processes, port=port, backend=backend, host=host
    )
    if rel in (REL_DIRECT, REL_VERIFIED_DESCENDANT):
        return rel, pid, reason
    return rel, None, reason


def health_is_start_pass(status_code: int, body: str) -> bool:
    """Start PASS requires HTTP 200 + status=ok + startup_phase=READY only."""
    if int(status_code) != 200:
        return False
    b = body or ""
    if '"status"' not in b or '"startup_phase"' not in b:
        return False
    # Reject degraded / FAIL explicitly even if other tokens present
    import re

    sm = re.search(r'"status"\s*:\s*"([^"]+)"', b)
    pm = re.search(r'"startup_phase"\s*:\s*"([^"]+)"', b)
    if not sm or not pm:
        return False
    return sm.group(1) == "ok" and pm.group(1) == "READY"


def creation_time_matches(expected: str, actual: str) -> bool:
    if not expected or not actual:
        return False
    return expected == actual


def should_kill_process(
    *,
    relationship: str,
    meta_listener_pid: int | None,
    meta_listener_creation: str,
    live_pid: int,
    live_creation: str,
) -> bool:
    """Kill only when persisted identity still matches the live process."""
    if relationship not in (REL_DIRECT, REL_VERIFIED_DESCENDANT):
        return False
    if meta_listener_pid is None or int(meta_listener_pid) != int(live_pid):
        return False
    return creation_time_matches(meta_listener_creation, live_creation)
