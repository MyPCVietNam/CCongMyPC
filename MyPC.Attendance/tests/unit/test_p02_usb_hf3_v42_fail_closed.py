"""HF3 V4.2 Prepare safety + PID record consistency contracts (no OS side effects)."""
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
    spec = importlib.util.spec_from_file_location("mypc_hf3_v42", source)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_r9_prepare_never_wipes_existing_src_before_gates():
    prep = _mode("Prepare", "Update")
    assert "Get-Hf3PortListenerOwnerPids" in prep
    assert "Get-Hf3LaunchMetaState" in prep
    assert "Invoke-Hf3PrepareHandler" in prep
    assert "EXIT_PREPARE_EXISTING_SOURCE" in PS
    # Live src must not be recursively force-removed for Prepare idempotency.
    assert "Remove-Item -Recurse -Force $srcDir" not in prep.split("Rename-Item -LiteralPath $stageSrc", 1)[0]
    assert "src-prepare-staging-" in prep


def test_r9_prepare_models_checked_before_staging():
    prep = _mode("Prepare", "Update")
    before_stage = prep.split("src-prepare-staging-", 1)[0]
    assert "Prepare requires -ModelsSourceDir" in before_stage
    assert "Invoke-Hf3PrepareHandler" in before_stage


def test_r9_prepare_handler_exit_codes():
    body = _fn("Invoke-Hf3PrepareHandler", "Invoke-Hf3StartHandler")
    for code in (
        "EXIT_PREPARE_INPUT_INVALID",
        "EXIT_PREPARE_EXISTING_SOURCE",
        "EXIT_PREPARE_PROCESS_UNKNOWN",
    ):
        assert code in body
    assert "Assert-Hf3CandidateRootSafe" in body


def test_r10_shared_pid_record_helpers():
    assert "function Get-Hf3PidRecordState" in PS
    assert "function Test-Hf3PidRecord" in PS
    pid = _fn("Test-Hf3PidRecord", "Invoke-Hf3PrepareHandler")
    for token in ("ABSENT", "INVALID", "MISMATCH", "LIVE_UNKNOWN", "MATCH_LIVE", "MATCH_ABSENT", "STALE_ABSENT"):
        assert token in pid


def test_r10_start_update_stop_check_pid_with_valid_meta():
    start_free = _mode("Start", "Stop").split("Stale metadata with free port", 1)[1].split("$launchNonce", 1)[0]
    before_else = start_free.split("} elseif (Test-Path $pidFile)", 1)[0]
    assert "Test-Hf3PidRecord" in before_else
    assert "EXIT_START_PID_RECORD_INCONSISTENT" in before_else or "Test-Hf3PidRecord" in before_else

    update_free = _mode("Update", "Preflight").split("Port free:", 1)[1].split("$backupLeaf", 1)[0]
    before_else_u = update_free.split("} elseif (Test-Path -LiteralPath $pidFile)", 1)[0]
    assert "Test-Hf3PidRecord" in before_else_u

    stop = _mode("Stop", "Diagnose")
    assert "Test-Hf3PidRecord" in stop or "Invoke-Hf3StopHandler" in stop
    assert "EXIT_STOP_PID_RECORD_INCONSISTENT" in PS


def test_r11_blank_listener_name_is_unverified():
    mod = load_helper()
    backend = r"C:\HF3\backend"
    cmd = r"python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 18878 --app-dir C:\HF3\backend"
    blank = mod.ProcessSnap(4242, "", 0, cmd, "2026-11-07T00:00:00Z")
    rel, _ = mod.classify_listener_ownership(blank, blank, {4242: blank}, port=18878, backend=backend)
    assert rel == mod.REL_UNVERIFIED
    conhost = mod.ProcessSnap(4242, "conhost.exe", 0, cmd, "2026-11-07T00:00:00Z")
    rel2, _ = mod.classify_listener_ownership(conhost, conhost, {4242: conhost}, port=18878, backend=backend)
    assert rel2 == mod.REL_UNVERIFIED
    good = mod.ProcessSnap(4242, "python.exe", 0, cmd, "2026-11-07T00:00:00Z")
    rel3, _ = mod.classify_listener_ownership(good, good, {4242: good}, port=18878, backend=backend)
    assert rel3 == mod.REL_DIRECT


def test_r12_harness_extracts_production_handlers_not_facades():
    assert "Extract-ModeText" in HARNESS
    assert "function Invoke-Hf3PrepareHandler" in PS
    assert "function Invoke-Hf3StartHandler" in PS
    assert "function Invoke-Hf3UpdateHandler" in PS
    assert "function Invoke-Hf3StopHandler" in PS
    # Harness must extract production functions, not redefine Start/Update/Stop facades.
    assert not re.search(r"(?m)^function Invoke-Hf3StartHandler\b", HARNESS)
    assert not re.search(r"(?m)^function Invoke-Hf3UpdateHandler\b", HARNESS)
    assert not re.search(r"(?m)^function Invoke-Hf3StopHandler\b", HARNESS)
    assert "Invoke-Hf3PrepareHandler" in HARNESS
    assert "Invoke-Hf3StartHandler" in HARNESS


def test_r12_prepare_mode_invokes_production_handler():
    prep = _mode("Prepare", "Update")
    assert "Invoke-Hf3PrepareHandler" in prep
    assert re.search(r"Extract-FunctionText[\s\S]*Invoke-Hf3PrepareHandler", HARNESS)
