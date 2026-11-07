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


def split_windows_cmdline(cmd: str) -> list[str]:
    """Approximate CommandLineToArgvW: whitespace split with double-quote grouping.

    Escaped quotes use an odd number of preceding backslashes. Sufficient for
    ownership checks of uvicorn argv including paths with spaces.
    """
    if not cmd:
        return []
    args: list[str] = []
    cur: list[str] = []
    in_quotes = False
    i = 0
    n = len(cmd)
    while i < n:
        ch = cmd[i]
        if ch == "\\":
            # Count run of backslashes
            bs = 0
            while i < n and cmd[i] == "\\":
                bs += 1
                i += 1
            if i < n and cmd[i] == '"':
                # Pairs of backslashes → literal \; odd trailing → escape the quote
                cur.extend(["\\"] * (bs // 2))
                if bs % 2 == 1:
                    cur.append('"')
                    i += 1
                else:
                    in_quotes = not in_quotes
                    i += 1
            else:
                cur.extend(["\\"] * bs)
            continue
        if ch == '"':
            in_quotes = not in_quotes
            i += 1
            continue
        if (ch == " " or ch == "\t") and not in_quotes:
            if cur:
                args.append("".join(cur))
                cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    if cur:
        args.append("".join(cur))
    return args


def _canon_win_path(p: str) -> str:
    return (p or "").strip().rstrip("\\/").lower().replace("/", "\\")


def _option_values(args: list[str], name: str) -> list[str]:
    """Collect values for --name value | --name=value. Missing value → __MISSING__."""
    out: list[str] = []
    i = 0
    key = name.lower()
    while i < len(args):
        a = args[i]
        al = a.lower()
        if al == key:
            if i + 1 >= len(args):
                out.append("__MISSING__")
                break
            out.append(args[i + 1])
            i += 2
            continue
        if al.startswith(key + "="):
            out.append(a.split("=", 1)[1])
            i += 1
            continue
        i += 1
    return out


# Safe interpreter flags (no value) allowed between python.exe and `-m uvicorn`.
_SAFE_PY_FLAGS_NO_VALUE = frozenset(
    {"-b", "-bb", "-B", "-E", "-I", "-O", "-OO", "-s", "-S", "-u", "-v", "-x"}
)


def _uvicorn_module_entrypoint_index(args: list[str]) -> int | None:
    """Index of ``-m`` when it is the interpreter module switch (not after ``-c``/script)."""
    if len(args) < 4:
        return None
    i = 1  # skip executable
    while i < len(args):
        a = args[i]
        al = a.lower()
        if al == "-c" or al.startswith("-c"):
            return None
        if al == "-m":
            if i + 2 < len(args) and args[i + 1].lower() == "uvicorn" and args[i + 2] == "app.main:app":
                return i
            return None
        if al in _SAFE_PY_FLAGS_NO_VALUE:
            i += 1
            continue
        # Any other token (script path, -c code, unknown flag) is not HF3 uvicorn entry.
        return None
    return None


def uvicorn_cmdline_matches(
    cmd: str,
    *,
    port: int,
    backend: str,
    host: str = "127.0.0.1",
) -> bool:
    """Require python → ``-m uvicorn app.main:app`` entrypoint + exact host/port/app-dir."""
    args = split_windows_cmdline(cmd or "")
    if len(args) < 5:
        return False
    # Reject foreign entrypoints and multi-process uvicorn modes.
    lowered = [a.lower() for a in args]
    if "-c" in lowered or any(a.startswith("-c") and a != "-c" for a in lowered):
        return False
    if "--reload" in lowered or "--workers" in lowered:
        return False
    m_idx = _uvicorn_module_entrypoint_index(args)
    if m_idx is None:
        return False
    hosts = _option_values(args, "--host")
    ports = _option_values(args, "--port")
    app_dirs = _option_values(args, "--app-dir")
    if len(hosts) != 1 or hosts[0] == "__MISSING__":
        return False
    if len(ports) != 1 or ports[0] == "__MISSING__":
        return False
    if len(app_dirs) != 1 or app_dirs[0] == "__MISSING__":
        return False
    if hosts[0] != host:
        return False
    if ports[0] != str(port):
        return False
    backend_n = _canon_win_path(backend)
    app_n = _canon_win_path(app_dirs[0])
    if not backend_n or app_n != backend_n:
        return False
    return True


def launcher_cleanup_outcome(
    *,
    launcher_pid: int,
    launcher_creation: str,
    launcher_alive: bool,
    stop_result: bool | None,
) -> str:
    """Tri-state Stop outcome when no listener remains on the port.

    Returns: absent | stopped | incomplete
    """
    if launcher_pid <= 0:
        return "absent"
    if not launcher_alive:
        return "absent"
    if not launcher_creation:
        return "incomplete"
    if stop_result is True:
        return "stopped"
    return "incomplete"


def kill_authorized(
    *,
    role: str,
    expected_creation: str,
    live_creation: str,
    is_conhost: bool,
    cmdline_ok: bool,
    is_python: bool,
    exe_matches_expected: bool,
) -> bool:
    """Mirror Stop-VerifiedHf3Identity fail-closed rules (no folder-substring auth)."""
    if is_conhost:
        return False
    if not expected_creation or not live_creation:
        return False
    if expected_creation != live_creation:
        return False
    if role == "listener":
        return bool(cmdline_ok)
    if role == "launcher":
        if not is_python:
            return False
        return bool(exe_matches_expected or cmdline_ok)
    return False


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
    """Start PASS requires HTTP 200 + top-level status=ok + startup_phase=READY."""
    if int(status_code) != 200:
        return False
    b = body or ""
    if not b.strip():
        return False
    import json

    try:
        obj = json.loads(b)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(obj, dict):
        return False
    # Nested status/startup_phase must not satisfy Start.
    return obj.get("status") == "ok" and obj.get("startup_phase") == "READY"


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
