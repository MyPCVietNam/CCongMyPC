#!/usr/bin/env python3
"""STRICTLY READ-ONLY inventory of camera secret filenames vs SQLite / outbox / leases.

When secrets/ exists but SQLite is missing/invalid/ambiguous/unreadable essential
tables, exit nonzero and mark inventory INCOMPLETE — never print zeros as success.

Never prints secret bytes. Never deletes/rotates/repairs. UNKNOWN ≠ ORPHAN.

Usage:
  python tools/audit_camera_secrets_readonly.py --data-dir <DISPOSABLE_DATADIR> [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

CAMERA_LIVE_RE = re.compile(r"^camera-(\d+)\.bin$")
CAMERA_STAGED_RE = re.compile(r"^camera-(\d+)\.staged-[0-9a-f]{32}\.bin$")
OUTBOX_ACTIVE = ("pending", "processing", "failed")


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    # URI path: absolute Windows/POSIX with spaces/unicode → percent-encode carefully
    resolved = db_path.resolve()
    # sqlite URI: forward slashes; quote special chars except /
    from urllib.parse import quote

    as_posix = resolved.as_posix()
    # Keep drive letter path like /C:/... for Windows absolute
    uri = "file:" + quote(as_posix, safe="/:") + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def audit_datadir(data: Path) -> dict:
    secrets = data / "secrets"
    leases_dir = secrets / "_staging_leases"
    report: dict = {
        "mode": "READ_ONLY",
        "inventory_status": "OK",
        "data_dir_basename": data.name,
        "secrets_dir_exists": secrets.is_dir(),
        "live_files": [],
        "staged_files": [],
        "other_allowlisted": [],
        "unknown_files": [],
        "sqlite_camera_secret_refs": [],
        "sqlite_includes_archived": True,
        "outbox_rows": [],
        "outbox_status_counts": {},
        "lease_files": [],
        "classifications": [],
        "incomplete_reasons": [],
        "note_vi": (
            "UNKNOWN = chưa chứng minh orphan. Không xóa khi còn outbox/lease. "
            "INCOMPLETE = thiếu/không đọc được SQLite hoặc bảng bắt buộc."
        ),
    }
    if not secrets.is_dir():
        report["inventory_status"] = "INCOMPLETE"
        report["incomplete_reasons"].append("MISSING_SECRETS_DIR")
        report["error"] = "MISSING_SECRETS_DIR"
        return report

    for f in sorted(secrets.iterdir()):
        if not f.is_file() or f.is_symlink():
            continue
        name = f.name
        if CAMERA_LIVE_RE.match(name):
            report["live_files"].append({"name": name, "bytes": f.stat().st_size})
        elif CAMERA_STAGED_RE.match(name):
            report["staged_files"].append({"name": name, "bytes": f.stat().st_size})
        elif name in {"master.key", "session.secret", "face_templates.key"}:
            report["other_allowlisted"].append({"name": name, "bytes": f.stat().st_size})
        else:
            report["unknown_files"].append(name)

    if leases_dir.is_dir():
        for f in sorted(leases_dir.iterdir()):
            if f.is_file() and f.name.endswith(".lease"):
                report["lease_files"].append(f.name)

    refs: set[str] = set()
    cam_ids_active: set[int] = set()
    cam_ids_all: set[int] = set()
    outbox_staged: set[str] = set()
    outbox_live: set[str] = set()
    outbox_delete: set[str] = set()
    lease_staged: set[str] = set()

    for lf in report["lease_files"]:
        if lf.endswith(".lease"):
            lease_staged.add(lf[: -len(".lease")])

    db_candidates: list[Path] = []
    for pattern in ("*.sqlite3", "*.db"):
        db_candidates.extend([p for p in data.glob(pattern) if p.is_file()])
    # Prefer attendance-like names; exclude -wal/-shm siblings already filtered by suffix
    db_candidates = sorted(
        {p.resolve() for p in db_candidates if not p.name.endswith(("-wal", "-shm"))}
    )

    if not db_candidates:
        report["inventory_status"] = "INCOMPLETE"
        report["incomplete_reasons"].append("SQLITE_MISSING")
    elif len(db_candidates) > 1:
        report["inventory_status"] = "INCOMPLETE"
        report["incomplete_reasons"].append("SQLITE_AMBIGUOUS")
        report["sqlite_candidates"] = [p.name for p in db_candidates]
    else:
        db_path = db_candidates[0]
        report["sqlite_basename"] = db_path.name
        try:
            con = _connect_readonly(db_path)
        except Exception as exc:  # noqa: BLE001
            report["inventory_status"] = "INCOMPLETE"
            report["incomplete_reasons"].append("SQLITE_OPEN_FAILED")
            report["sqlite_error"] = type(exc).__name__
            con = None
        if con is not None:
            try:
                tables = {
                    r[0]
                    for r in con.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if "camera_devices" not in tables:
                    report["inventory_status"] = "INCOMPLETE"
                    report["incomplete_reasons"].append("MISSING_TABLE_camera_devices")
                else:
                    rows = con.execute(
                        "SELECT id, secret_ref, COALESCE(archived,0) FROM camera_devices"
                    ).fetchall()
                    for cid, ref, archived in rows:
                        cam_ids_all.add(int(cid))
                        if not int(archived or 0):
                            cam_ids_active.add(int(cid))
                        if ref:
                            refs.add(str(ref))
                            report["sqlite_camera_secret_refs"].append(
                                {
                                    "camera_id": int(cid),
                                    "secret_ref": str(ref),
                                    "archived": bool(int(archived or 0)),
                                }
                            )
                if "secret_fs_outbox" not in tables:
                    report["inventory_status"] = "INCOMPLETE"
                    report["incomplete_reasons"].append("MISSING_TABLE_secret_fs_outbox")
                else:
                    ob = con.execute(
                        "SELECT public_id, status, staged_ref, live_ref, delete_ref, camera_id "
                        "FROM secret_fs_outbox"
                    ).fetchall()
                    for public_id, status, staged_ref, live_ref, delete_ref, camera_id in ob:
                        st = str(status or "")
                        report["outbox_status_counts"][st] = (
                            report["outbox_status_counts"].get(st, 0) + 1
                        )
                        report["outbox_rows"].append(
                            {
                                "public_id": str(public_id),
                                "status": st,
                                "camera_id": camera_id,
                                "has_staged_ref": bool(staged_ref),
                                "has_live_ref": bool(live_ref),
                                "has_delete_ref": bool(delete_ref),
                                "staged_ref": str(staged_ref or "") or None,
                                "live_ref": str(live_ref or "") or None,
                                "delete_ref": str(delete_ref or "") or None,
                            }
                        )
                        if st in OUTBOX_ACTIVE:
                            if staged_ref:
                                outbox_staged.add(str(staged_ref))
                            if live_ref:
                                outbox_live.add(str(live_ref))
                            if delete_ref:
                                outbox_delete.add(str(delete_ref))
            except sqlite3.Error as exc:
                report["inventory_status"] = "INCOMPLETE"
                report["incomplete_reasons"].append("SQLITE_QUERY_FAILED")
                report["sqlite_error"] = type(exc).__name__
            finally:
                con.close()

    live_names = {x["name"] for x in report["live_files"]}
    staged_names = {x["name"] for x in report["staged_files"]}

    # Classifications only meaningful when inventory complete enough to compare refs
    can_classify = report["inventory_status"] == "OK"
    for name in sorted(live_names):
        reasons = []
        if not can_classify:
            label = "UNKNOWN"
            reasons.append("inventory_incomplete")
        elif name in refs:
            label = "REFERENCED"
            reasons.append("sqlite_secret_ref")
            if name in outbox_live or name in outbox_delete:
                reasons.append("outbox_active_ref")
        elif name in outbox_live or name in outbox_delete:
            label = "REFERENCED"
            reasons.append("outbox_active_ref")
        else:
            label = "UNKNOWN"
            reasons.append("no_sqlite_or_active_outbox_ref")
        report["classifications"].append(
            {"name": name, "kind": "live", "label": label, "reasons": reasons}
        )

    for name in sorted(staged_names):
        reasons = []
        if not can_classify:
            label = "UNKNOWN"
            reasons.append("inventory_incomplete")
        elif name in outbox_staged or name in lease_staged:
            label = "IN_FLIGHT"
            if name in outbox_staged:
                reasons.append("outbox_active_staged_ref")
            if name in lease_staged:
                reasons.append("lease_file_present")
        else:
            label = "UNKNOWN"
            reasons.append("no_active_outbox_or_lease")
        report["classifications"].append(
            {"name": name, "kind": "staged", "label": label, "reasons": reasons}
        )

    report["counts"] = {
        "cameras_all": len(cam_ids_all),
        "cameras_active": len(cam_ids_active),
        "live_files": len(live_names),
        "staged_files": len(staged_names),
        "sqlite_refs": len(refs),
        "unknown_label": sum(1 for c in report["classifications"] if c["label"] == "UNKNOWN"),
        "in_flight": sum(1 for c in report["classifications"] if c["label"] == "IN_FLIGHT"),
        "referenced": sum(1 for c in report["classifications"] if c["label"] == "REFERENCED"),
        "leases": len(report["lease_files"]),
    }
    report["orphan_live_candidates"] = []
    report["orphan_staged_candidates"] = []
    report["pending_outbox_count"] = report["outbox_status_counts"].get("pending", 0)
    report["processing_outbox_count"] = report["outbox_status_counts"].get("processing", 0)
    report["failed_outbox_count"] = report["outbox_status_counts"].get("failed", 0)
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, required=True)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    report = audit_datadir(args.data_dir.resolve())
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        c = report.get("counts") or {}
        print(
            f"inventory={report.get('inventory_status')} "
            f"cameras_all={c.get('cameras_all')} active={c.get('cameras_active')} "
            f"live={c.get('live_files')} staged={c.get('staged_files')} "
            f"referenced={c.get('referenced')} in_flight={c.get('in_flight')} "
            f"unknown={c.get('unknown_label')} "
            f"reasons={report.get('incomplete_reasons')}"
        )
        print("READ_ONLY — no deletions; UNKNOWN ≠ proven orphan; INCOMPLETE ≠ success")
    if report.get("inventory_status") != "OK":
        return 3
    if not report.get("secrets_dir_exists"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
