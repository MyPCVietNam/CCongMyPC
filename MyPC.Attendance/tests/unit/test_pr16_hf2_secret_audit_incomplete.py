"""PR16-HF2: secret inventory INCOMPLETE when SQLite missing/corrupt."""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location(
    "audit_camera_secrets_readonly", ROOT / "tools" / "audit_camera_secrets_readonly.py"
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)
audit_datadir = _mod.audit_datadir


def test_missing_sqlite_incomplete(tmp_path: Path):
    data = tmp_path / "d"
    (data / "secrets").mkdir(parents=True)
    (data / "secrets" / "camera-1.bin").write_bytes(b"x" * 8)
    report = audit_datadir(data)
    assert report["inventory_status"] == "INCOMPLETE"
    assert "SQLITE_MISSING" in report["incomplete_reasons"]
    assert report["counts"]["live_files"] == 1
    # classifications UNKNOWN due to incomplete — never ORPHAN
    assert all(c["label"] != "ORPHAN" for c in report["classifications"])


def test_corrupt_sqlite_incomplete(tmp_path: Path):
    data = tmp_path / "d2"
    (data / "secrets").mkdir(parents=True)
    (data / "broken.sqlite3").write_bytes(b"not a database")
    report = audit_datadir(data)
    assert report["inventory_status"] == "INCOMPLETE"
    assert any(
        r in report["incomplete_reasons"]
        for r in ("SQLITE_OPEN_FAILED", "SQLITE_QUERY_FAILED")
    )


def test_missing_outbox_table_incomplete(tmp_path: Path):
    data = tmp_path / "d3"
    secrets = data / "secrets"
    secrets.mkdir(parents=True)
    db = data / "attendance.sqlite3"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE camera_devices (id INTEGER PRIMARY KEY, secret_ref TEXT, archived INTEGER DEFAULT 0)"
    )
    con.commit()
    con.close()
    report = audit_datadir(data)
    assert report["inventory_status"] == "INCOMPLETE"
    assert "MISSING_TABLE_secret_fs_outbox" in report["incomplete_reasons"]
