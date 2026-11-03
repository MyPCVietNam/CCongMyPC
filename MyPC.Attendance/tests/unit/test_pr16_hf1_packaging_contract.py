"""PR16-HF1 packaging contract helpers."""

from __future__ import annotations

from pathlib import Path


def test_packager_exists():
    root = Path(__file__).resolve().parents[2]
    assert (root / "tools" / "package_pr16_hf1_complete_audit.py").is_file()


def test_handoff_docs_exist():
    hand = Path(__file__).resolve().parents[2] / "audit/handoffs/PR16-HF1-CORRECTIVE-20261103"
    for name in ("BASELINE_RCA.md", "CHANGELOG.md", "ACCEPTANCE_MATRIX.md", "README.md"):
        assert (hand / name).is_file()
