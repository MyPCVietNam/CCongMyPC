#!/usr/bin/env python3
"""STRICTLY READ-ONLY inventory of camera secret filenames vs SQLite / outbox / leases.

Never prints secret bytes, passwords, or key material.
Never deletes, rotates, or resets. Ambiguous files are labeled UNKNOWN — not ORPHAN.

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


def audit_datadir(data: Path) -> dict:
    secrets = data / "secrets"
    leases_dir = secrets / "_staging_leases"
    report: dict = {
        "mode": "READ_ONLY",
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
        "note_vi": (
            "UNKNOWN = chưa chứng minh orphan. Không xóa khi còn outbox pending/processing/failed "
            "hoặc lease. Cần backup + rollback trước cleanup thủ công."
        ),
    }
    if not secrets.is_dir():
        report["error"] = "MISSING_SECRETS_DIR"
        return report

    for f in sorted(secrets.iterdir()):
        if not f.is_file() or f.is_symlink():
            continue
        if f.parent.name == "_staging_leases":
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
        # camera-1.staged-<hex>.bin.lease
        if lf.endswith(".lease"):
            lease_staged.add(lf[: -len(".lease")])

    db_candidates = []
    for pattern in ("*.sqlite3", "mypc*.db", "*.db"):
        db_candidates.extend(data.glob(pattern))
    # Prefer attendance.sqlite3 / mypc.sqlite3 style
    db_path = None
    for c in db_candidates:
        if c.is_file() and not c.name.endswith(("-wal", "-shm")):
            db_path = c
            break
    if db_path is None:
        for c in data.iterdir():
            if c.suffix == ".sqlite3" or c.name.endswith(".db"):
                db_path = c
                break

    if db_path is not None:
        try:
            # Read-only URI works with WAL (does not create writer lock)
            con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
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
                try:
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
                                # names only — never open blobs
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
                except sqlite3.Error:
                    report["outbox_status_counts"] = {"error": "table_unavailable"}
            finally:
                con.close()
        except Exception as exc:  # noqa: BLE001
            report["sqlite_error"] = type(exc).__name__

    live_names = {x["name"] for x in report["live_files"]}
    staged_names = {x["name"] for x in report["staged_files"]}

    for name in sorted(live_names):
        reasons = []
        if name in refs:
            reasons.append("sqlite_secret_ref")
        if name in outbox_live or name in outbox_delete:
            reasons.append("outbox_active_ref")
        if reasons:
            label = "REFERENCED"
        else:
            label = "UNKNOWN"  # never ORPHAN without proof
            reasons.append("no_sqlite_or_active_outbox_ref")
        report["classifications"].append(
            {"name": name, "kind": "live", "label": label, "reasons": reasons}
        )

    for name in sorted(staged_names):
        reasons = []
        if name in outbox_staged:
            reasons.append("outbox_active_staged_ref")
        if name in lease_staged:
            reasons.append("lease_file_present")
        if reasons:
            label = "IN_FLIGHT"
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
    # Legacy keys kept for operators — empty; use classifications
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
            f"cameras_all={c.get('cameras_all')} active={c.get('cameras_active')} "
            f"live={c.get('live_files')} staged={c.get('staged_files')} "
            f"referenced={c.get('referenced')} in_flight={c.get('in_flight')} "
            f"unknown={c.get('unknown_label')} "
            f"outbox_pending={report.get('pending_outbox_count')} "
            f"processing={report.get('processing_outbox_count')} "
            f"failed={report.get('failed_outbox_count')}"
        )
        print("READ_ONLY — no deletions; UNKNOWN ≠ proven orphan")
    return 0 if report.get("secrets_dir_exists") else 2


if __name__ == "__main__":
    raise SystemExit(main())
