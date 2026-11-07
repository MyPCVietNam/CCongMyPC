"""Fake-directory Update promotion/rollback (no real candidate / no Windows required).

Mirrors the PS 5.1 leaf-rename semantics used by
``scripts/windows/p02_usb_hf3_candidate_18878.ps1 -Mode Update``:
Rename-Item -NewName must be a leaf under the same parent, never an absolute path.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def _leaf_rename(src: Path, new_leaf: str) -> Path:
    """Same-parent rename: equivalent to Rename-Item -LiteralPath -NewName <leaf>."""
    if "/" in new_leaf or "\\" in new_leaf:
        raise ValueError("NewName must be a leaf name, not a path")
    dest = src.parent / new_leaf
    src.rename(dest)
    return dest


def _promote_src(candidate_root: Path, stage_name: str = "src-update-staging") -> Path:
    src = candidate_root / "src"
    stage = candidate_root / stage_name
    backup_leaf = "src-backup-test"
    assert stage.is_dir()
    assert (stage / "MyPC.Attendance" / "backend" / "app" / "main.py").is_file()
    if src.exists():
        _leaf_rename(src, backup_leaf)
    _leaf_rename(stage, "src")
    return candidate_root / backup_leaf


def _rollback(candidate_root: Path, backup: Path) -> None:
    src = candidate_root / "src"
    if src.exists():
        shutil.rmtree(src)
    _leaf_rename(backup, "src")


def test_update_leaf_rename_promotes_and_preserves_datadir(tmp_path: Path):
    root = tmp_path / "p02-usb-hf3-candidate"
    data = root / "DataDir"
    models = root / "models" / "weights"
    src = root / "src"
    stage = root / "src-update-staging"
    for d in (data, models, src, stage):
        d.mkdir(parents=True)
    (data / "keep.sqlite3").write_text("SECRET_MUST_SURVIVE", encoding="utf-8")
    (models / "face_detection_yunet_2023mar.onnx").write_bytes(b"PIN")
    old_marker = src / "OLD.txt"
    old_marker.write_text("old-src", encoding="utf-8")
    staged_main = stage / "MyPC.Attendance" / "backend" / "app" / "main.py"
    staged_main.parent.mkdir(parents=True)
    staged_main.write_text("# new", encoding="utf-8")

    backup = _promote_src(root)
    assert (root / "src" / "MyPC.Attendance" / "backend" / "app" / "main.py").is_file()
    assert not (root / "src" / "OLD.txt").exists()
    assert backup.is_dir()
    assert (backup / "OLD.txt").read_text(encoding="utf-8") == "old-src"
    assert (data / "keep.sqlite3").read_text(encoding="utf-8") == "SECRET_MUST_SURVIVE"
    assert (models / "face_detection_yunet_2023mar.onnx").read_bytes() == b"PIN"


def test_update_rollback_restores_previous_src(tmp_path: Path):
    root = tmp_path / "p02-usb-hf3-candidate"
    src = root / "src"
    stage = root / "src-update-staging"
    src.mkdir(parents=True)
    (src / "OLD.txt").write_text("old-src", encoding="utf-8")
    staged_main = stage / "MyPC.Attendance" / "backend" / "app" / "main.py"
    staged_main.parent.mkdir(parents=True)
    staged_main.write_text("# bad-new", encoding="utf-8")

    backup = _promote_src(root)
    # Simulate pip / post-promote failure → rollback
    _rollback(root, backup)
    assert (root / "src" / "OLD.txt").read_text(encoding="utf-8") == "old-src"
    assert not (root / "src" / "MyPC.Attendance").exists()


def test_leaf_rename_rejects_absolute_newname(tmp_path: Path):
    d = tmp_path / "src"
    d.mkdir()
    try:
        _leaf_rename(d, str(tmp_path / "src-backup-abs"))
        raised = False
    except ValueError:
        raised = True
    assert raised
