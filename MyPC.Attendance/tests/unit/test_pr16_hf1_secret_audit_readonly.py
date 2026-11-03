"""PR16-HF1: read-only secret inventory — archived, outbox, leases, UNKNOWN≠ORPHAN."""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location(
    "audit_camera_secrets_readonly", TOOLS / "audit_camera_secrets_readonly.py"
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)
audit_datadir = _mod.audit_datadir


def _init_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE camera_devices (
          id INTEGER PRIMARY KEY,
          secret_ref TEXT,
          archived INTEGER DEFAULT 0
        );
        CREATE TABLE secret_fs_outbox (
          id INTEGER PRIMARY KEY,
          public_id TEXT,
          camera_id INTEGER,
          op TEXT,
          staged_ref TEXT,
          live_ref TEXT,
          delete_ref TEXT,
          status TEXT
        );
        """
    )
    con.commit()
    con.close()


def test_archived_refs_and_outbox_states(tmp_path: Path):
    data = tmp_path / "datadir"
    secrets = data / "secrets"
    leases = secrets / "_staging_leases"
    secrets.mkdir(parents=True)
    leases.mkdir()
    (secrets / "camera-1.bin").write_bytes(b"x" * 32)
    (secrets / "camera-2.bin").write_bytes(b"y" * 32)
    staged = "camera-1.staged-" + ("ab" * 16) + ".bin"
    (secrets / staged).write_bytes(b"z" * 16)
    orphan_staged = "camera-9.staged-" + ("cd" * 16) + ".bin"
    (secrets / orphan_staged).write_bytes(b"q" * 8)
    (leases / f"{staged}.lease").write_text("lease")

    db = data / "attendance.sqlite3"
    _init_db(db)
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO camera_devices(id, secret_ref, archived) VALUES (1,'camera-1.bin',0)"
    )
    con.execute(
        "INSERT INTO camera_devices(id, secret_ref, archived) VALUES (2,'camera-2.bin',1)"
    )
    con.execute(
        "INSERT INTO secret_fs_outbox(public_id,camera_id,op,staged_ref,live_ref,delete_ref,status) "
        "VALUES ('p1',1,'promote',?,?,?,'pending')",
        (staged, "camera-1.bin", ""),
    )
    con.execute(
        "INSERT INTO secret_fs_outbox(public_id,camera_id,op,staged_ref,live_ref,delete_ref,status) "
        "VALUES ('p2',1,'promote','','','camera-x.bin','processing')"
    )
    con.execute(
        "INSERT INTO secret_fs_outbox(public_id,camera_id,op,staged_ref,live_ref,delete_ref,status) "
        "VALUES ('p3',1,'delete','','','camera-old.bin','failed')"
    )
    con.commit()
    con.close()

    # Also create a WAL sibling to ensure RO open still works
    (data / "attendance.sqlite3-wal").write_bytes(b"walstub")

    report = audit_datadir(data)
    assert report["mode"] == "READ_ONLY"
    assert report["counts"]["cameras_all"] == 2
    assert report["counts"]["cameras_active"] == 1
    assert report["pending_outbox_count"] == 1
    assert report["processing_outbox_count"] == 1
    assert report["failed_outbox_count"] == 1

    by_name = {c["name"]: c for c in report["classifications"]}
    assert by_name["camera-1.bin"]["label"] == "REFERENCED"
    assert by_name["camera-2.bin"]["label"] == "REFERENCED"  # archived still counted
    assert by_name[staged]["label"] == "IN_FLIGHT"
    assert by_name[orphan_staged]["label"] == "UNKNOWN"
    assert report["orphan_live_candidates"] == []
    assert report["orphan_staged_candidates"] == []


def test_import_path_for_pytest():
    # ensure package import via tools path works when cwd is MyPC.Attendance
    assert callable(audit_datadir)
