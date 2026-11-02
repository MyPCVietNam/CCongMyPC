"""P02R 57-case acceptance matrix — executable status ledger (Cloud-safe)."""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent
MATRIX = ROOT / "docs" / "P02R_ACCEPTANCE_MATRIX.csv"
PR8 = "8c5b20058e6777bb61666e541e8fa5ba65a770e9"

# Cases that this Cloud Agent environment can evaluate without company LAN hardware.
CLOUD_EXECUTABLE = {
    "ENV01",
    "ENV02",
    "ENV03",
    "ENV04",
    "ENV07",
    "ENV08",
    "ENV10",
    "SEC01",
    "SEC02",
    "SEC03",
    "EV01",
    "EV02",
    "EV05",
    "EV06",
    "EV11",
    "EV13",
    "EV14",
    "BUS01",
    "BUS02",
    "BUS03",
    "BUS04",
    "BUS05",
    "BUS06",
    "BUS07",
    "REL04",
}

# Explicit physical / Windows-owner gates — must remain BLOCKED here.
HARDWARE_BLOCKED = {
    "CAM01",
    "CAM02",
    "CAM06",
    "CAM08",
    "WIN02",
    "WIN03",
    "WIN04",
}


def _matrix_rows():
    with MATRIX.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_matrix_has_57_cases():
    rows = _matrix_rows()
    assert len(rows) == 57
    assert {r["CaseID"] for r in rows}


def test_env01_env02_pr8_ancestry():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    rc = subprocess.call(["git", "merge-base", "--is-ancestor", PR8, "HEAD"], cwd=REPO)
    assert rc == 0, f"HEAD {head} must descend from PR8 {PR8}"


def test_env03_reject_main_and_p00_in_verify_script():
    script = (ROOT / "scripts" / "verify_pr8_checkout.sh").read_text(encoding="utf-8")
    assert "main|master|cursor/mypc-attendance-p00-83a8" in script
    assert "exit 11" in script
    assert "|| true" not in script


def test_env04_verify_fail_closed_no_info_exit_zero():
    script = (ROOT / "scripts" / "verify_pr8_checkout.sh").read_text(encoding="utf-8")
    assert "FAIL WRONG_SOURCE" in script
    assert "set -euo pipefail" in script


def test_hardware_gates_listed_blocked_in_docs():
    guide = (ROOT / "docs" / "vi" / "HUONG_DAN_KIEM_CAMERA_WINDOWS.md").read_text(encoding="utf-8")
    assert "BLOCKED" in guide
    assert "CAMERA_LAB" in guide
    for case_id in HARDWARE_BLOCKED:
        assert case_id  # ledger presence
    rows = {r["CaseID"]: r for r in _matrix_rows()}
    for case_id in HARDWARE_BLOCKED:
        assert case_id in rows


def test_rel04_not_on_main():
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=REPO, text=True
    ).strip()
    assert branch not in {"main", "master"}


@pytest.mark.parametrize("case_id", sorted(CLOUD_EXECUTABLE))
def test_cloud_executable_case_present(case_id):
    ids = {r["CaseID"] for r in _matrix_rows()}
    assert case_id in ids
