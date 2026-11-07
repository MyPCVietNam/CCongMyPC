#!/usr/bin/env python3
"""Repository quality contracts. No external dependencies or host-side effects.

    python quality_guard/check.py --root . --selftest
    python quality_guard/check.py --root . --strict

--strict deliberately fails on unsafe legacy HF3 code until corrected; do not
suppress the failure. It never starts/kills a process or reads owner DataDir.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def find_issues(root: Path, strict: bool = True) -> list[str]:
    issues: list[str] = []
    required = [
        "AGENTS.md", ".cursor/hooks.json", ".cursor/hooks/guard-shell.cjs",
        ".cursor/skills/mypc-safe-change/SKILL.md",
        ".github/workflows/mypc-quality-guard.yml",
    ]
    for rel in required:
        if not (root / rel).is_file():
            issues.append(f"FRAMEWORK_FILE_MISSING: {rel}")
    try:
        hook = json.loads((root / ".cursor/hooks.json").read_text(encoding="utf-8"))
        if hook.get("version") != 1:
            issues.append("HOOK_SCHEMA_VERSION_NOT_1")
        hooks = hook.get("hooks", {}).get("beforeShellExecution", [])
        if not hooks or not all(h.get("failClosed") is True for h in hooks):
            issues.append("HOOK_NOT_FAIL_CLOSED")
    except (OSError, ValueError, TypeError):
        issues.append("HOOK_JSON_INVALID")

    rules = list((root / ".cursor/rules").glob("*.mdc"))
    if len(rules) < 4:
        issues.append("PROJECT_RULES_INCOMPLETE")
    for f in rules:
        txt = f.read_text(encoding="utf-8-sig")
        if not re.match(r"\A---\r?\n.*?\r?\n---\r?\n", txt, re.S):
            issues.append(f"RULE_FRONTMATTER_INVALID: {f.name}")

    if not strict:
        return issues

    psdir = root / "MyPC.Attendance/scripts/windows"
    if not psdir.is_dir():
        issues.append("BACKEND_SOURCE_MISSING: MyPC.Attendance/scripts/windows")
        return issues
    for path in psdir.rglob("*.ps1"):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if re.search(r"\bforeach\s*\(\s*\$pid\b", text, re.I):
            issues.append(f"PS_RESERVED_PID: {path.relative_to(root).as_posix()}")

    runtime_test = psdir / "p02_usb_hf3_pid_safety_runtime_tests.ps1"
    if runtime_test.is_file():
        s = runtime_test.read_text(encoding="utf-8-sig", errors="replace")
        # A simulated WMI snapshot must NEVER reach a real Stop-Process call.
        if re.search(r"\bStop-VerifiedHf3Identity\s+-TargetPid\s+4242\b", s, re.I):
            issues.append("HF3_SYNTHETIC_FAKE_PID_REACHES_KILL_BOUNDARY")
        if re.search(r"(?m)^\s*(?:try\s*\{\s*)?Stop-Process\b", s, re.I):
            issues.append("HF3_SYNTHETIC_RUNTIME_CALLS_REAL_STOP_PROCESS")
        if re.search(r"(?i)Microsoft\.PowerShell\.Management\\Stop-Process", s):
            issues.append("HF3_SYNTHETIC_LAB_REAL_QUALIFIED_STOP_PROCESS")

    hf3 = psdir / "p02_usb_hf3_candidate_18878.ps1"
    if hf3.is_file():
        s = hf3.read_text(encoding="utf-8-sig", errors="replace")
        block = re.search(r"(?is)function\s+Test-Hf3UvicornCommandLine\b(.{0,4000}?)\bfunction\s+Test-IsPythonProcessName", s)
        if block and re.search(r"\bIndexOf\s*\(\s*\$backendNorm", block.group(1), re.I):
            issues.append("HF3_PS_BACKEND_SUBSTRING_AUTHORIZATION")
        if block and re.search(r"for\s*\(\s*\$i\s*=\s*0;\s*\$i\s*-lt\s*\(\$argv\.Count\s*-\s*1\)", block.group(1), re.I):
            issues.append("HF3_PS_UVICORN_ANYWHERE_SCAN")
        start = re.search(r'(?is)"Start"\s*\{(.{0,12000}?)"Stop"\s*\{', s)
        if start:
            free = start.group(1)
            if "Stale metadata with free port" in free or "port is free" in free:
                if ("Get-Hf3LaunchMetaState" not in free and "Read-Hf3LaunchMeta" not in free) or "Get-Win32ProcessById" not in free:
                    issues.append("HF3_START_FREE_PORT_CLEARS_META_WITHOUT_PROBE")
                if "EXIT_START_STALE_LAUNCHER" not in free:
                    issues.append("HF3_START_MISSING_STALE_LAUNCHER_EXIT")
                if "EXIT_START_INVALID_LAUNCH_META" not in free:
                    issues.append("HF3_START_MISSING_INVALID_META_EXIT")
        stop = re.search(r'(?is)"Stop"\s*\{(.{0,6000}?)"Diagnose"\s*\{', s)
        if stop and "EXIT_STOP_INVALID_LAUNCH_META" not in stop.group(1):
            issues.append("HF3_STOP_MISSING_INVALID_META_EXIT")
        update = re.search(r'(?is)"Update"\s*\{(.{0,14000}?)"Preflight"\s*\{', s)
        if update:
            u = update.group(1)
            if "EXIT_UPDATE_INVALID_LAUNCH_META" not in u:
                issues.append("HF3_UPDATE_MISSING_INVALID_META_EXIT")
            if "listener_pid" not in u or "EXIT_UPDATE_STALE_LISTENER" not in u:
                issues.append("HF3_UPDATE_FREE_PORT_MISSING_LISTENER_CHECK")
        getproc = re.search(r"(?is)function\s+Get-Win32ProcessById\b(.{0,800}?)\bfunction\s+", s)
        if getproc and "-ErrorAction SilentlyContinue" in getproc.group(1):
            issues.append("HF3_PROCESS_PROBE_SILENT_ABSENCE")
        gettcp = re.search(r"(?is)function\s+Get-Hf3PortListenerOwnerPids\b(.{0,900}?)\bfunction\s+", s)
        if gettcp and "-ErrorAction SilentlyContinue" in gettcp.group(1):
            issues.append("HF3_TCP_PROBE_SILENT_FREE_PORT")
        if "function Get-Hf3LaunchMetaState" not in s:
            issues.append("HF3_LAUNCH_META_STATE_HELPER_MISSING")
        if "Format-Hf3UvicornProcessArguments" not in s:
            issues.append("HF3_UVICORN_ARGV_QUOTING_HELPER_MISSING")
        live = re.search(r"(?is)function\s+Test-LiveMatchesLaunchMeta\b(.{0,2000}?)\bfunction\s+Stop-VerifiedHf3Identity", s)
        if live and "Test-IsPythonProcessName" not in live.group(1):
            issues.append("HF3_LIVE_MATCH_MISSING_PYTHON_NAME")
        resolve = re.search(r"(?is)function\s+Resolve-Hf3ListenerOwnership\b(.{0,3500}?)\bfunction\s+Test-Hf3HealthStartPass", s)
        if resolve:
            direct = resolve.group(1).split("if ($listenerPid -eq $LauncherPid)", 1)
            if len(direct) > 1:
                chunk = direct[1].split("if (-not (Test-IsPythonProcessName", 1)[0]
                if "Test-IsPythonProcessName $listener.Name" not in chunk:
                    issues.append("HF3_DIRECT_LISTENER_MISSING_PYTHON_NAME_CHECK")
    else:
        issues.append("HF3_SCRIPT_MISSING")
    return issues


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("."))
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--strict", action="store_true")
    mode.add_argument("--selftest", action="store_true")
    a = p.parse_args()
    issues = find_issues(a.root.resolve(), strict=a.strict)
    print(json.dumps({"mode": "strict" if a.strict else "framework_selftest",
                      "result": "PASS" if not issues else "BLOCKED",
                      "issue_count": len(issues), "codes": issues}, indent=2))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
