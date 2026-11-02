"""P02S 58-case acceptance matrix ledger (Cloud-safe executable subset)."""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parent
MATRIX = ROOT / "docs" / "P02S_ACCEPTANCE_MATRIX.csv"
PR9 = "3bd84dfb4dc779bb2c1709b2bd04bbc8843c7f87"
PR8 = "8c5b20058e6777bb61666e541e8fa5ba65a770e9"


def _rows():
    with MATRIX.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_matrix_has_58_cases():
    assert len(_rows()) == 58


def test_src01_pr9_ancestry():
    rc = subprocess.call(["git", "merge-base", "--is-ancestor", PR9, "HEAD"], cwd=REPO)
    assert rc == 0
    rc8 = subprocess.call(["git", "merge-base", "--is-ancestor", PR8, "HEAD"], cwd=REPO)
    assert rc8 == 0


def test_src02_verify_pr9_rejects_pr8_only_claim():
    script = (ROOT / "scripts" / "verify_pr9_checkout.sh").read_text(encoding="utf-8")
    assert PR9 in script
    assert "PR8-only is insufficient" in script or "not an ancestor of HEAD" in script
    assert "verify_pr9_checkout.sh || true" not in (
        ROOT / "scripts" / "cloud_setup_pr9.sh"
    ).read_text(encoding="utf-8")


def test_sec01_powershell_no_session_cookie_params():
    lab = (ROOT / "scripts" / "windows" / "Invoke-MyPCLabRun.ps1").read_text(encoding="utf-8")
    diag = (ROOT / "scripts" / "windows" / "Invoke-MyPCCameraDiagnostics.ps1").read_text(
        encoding="utf-8"
    )
    assert "DEPRECATED" in lab
    assert "param(" not in lab.lower() or "param()" in lab.replace(" ", "")
    assert "[Parameter" not in lab
    assert "[Parameter" not in diag
    assert "exit 2" in lab
    assert "exit 2" in diag


def test_sec02_api_lab_run_out_no_challenge_field_in_helper_docs():
    cams = (ROOT / "backend" / "app" / "api" / "cameras.py").read_text(encoding="utf-8")
    # _lab_run_out must not expose owner_challenge key in sanitized view
    assert '"owner_challenge": run.owner_challenge' not in cams
    assert "challenge_issued" in cams


def test_win01_readiness_pr9_pin():
    ps = (ROOT / "scripts" / "windows" / "Readiness-PR9.ps1").read_text(encoding="utf-8")
    assert PR9 in ps
    assert "pr9.preflight" in ps or "PR9" in ps


def test_ui_windows_lab_page_exists():
    page = ROOT / "frontend" / "src" / "pages" / "WindowsLabPage.tsx"
    assert page.is_file()
    text = page.read_text(encoding="utf-8")
    assert "owner-challenge" in text
    assert "PowerShell" in text
