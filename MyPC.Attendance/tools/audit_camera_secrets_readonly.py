#!/usr/bin/env python3
"""READ-ONLY inventory of camera secret filenames vs SQLite references.

Never prints secret bytes, passwords, or key material.
Never deletes staged/live blobs. Default mode is report-only.

Usage:
  python tools/audit_camera_secrets_readonly.py --data-dir <DISPOSABLE_DATADIR>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CAMERA_LIVE_RE = re.compile(r"^camera-(\d+)\.bin$")
CAMERA_STAGED_RE = re.compile(r"^camera-(\d+)\.staged-[0-9a-f]{32}\.bin$")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, required=True)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    data = args.data_dir.resolve()
    secrets = data / "secrets"
    report: dict = {
        "mode": "READ_ONLY",
        "data_dir_basename": data.name,
        "secrets_dir_exists": secrets.is_dir(),
        "live_files": [],
        "staged_files": [],
        "other_allowlisted": [],
        "unknown_files": [],
        "sqlite_camera_secret_refs": [],
        "orphan_live_candidates": [],
        "orphan_staged_candidates": [],
        "pending_outbox_count": None,
        "note_vi": (
            "Ứng viên orphan chỉ là gợi ý metadata — không xóa khi còn lease/outbox/transaction. "
            "Cần backup + quy trình rollback trước cleanup."
        ),
    }
    if not secrets.is_dir():
        print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else "MISSING secrets/")
        return 2

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

    # SQLite refs (optional)
    db_candidates = list(data.glob("*.sqlite3")) + list(data.glob("mypc*.sqlite3"))
    refs: set[str] = set()
    cam_ids: set[int] = set()
    if db_candidates:
        try:
            import sqlite3

            con = sqlite3.connect(f"file:{db_candidates[0]}?mode=ro", uri=True)
            try:
                rows = con.execute(
                    "SELECT id, secret_ref FROM camera_devices WHERE COALESCE(archived,0)=0"
                ).fetchall()
                for cid, ref in rows:
                    cam_ids.add(int(cid))
                    if ref:
                        refs.add(str(ref))
                        report["sqlite_camera_secret_refs"].append(
                            {"camera_id": int(cid), "secret_ref": str(ref)}
                        )
                try:
                    pending = con.execute(
                        "SELECT COUNT(*) FROM secret_fs_outbox WHERE status='pending'"
                    ).fetchone()
                    report["pending_outbox_count"] = int(pending[0]) if pending else 0
                except sqlite3.Error:
                    report["pending_outbox_count"] = None
            finally:
                con.close()
        except Exception as exc:  # noqa: BLE001
            report["sqlite_error"] = type(exc).__name__

    live_names = {x["name"] for x in report["live_files"]}
    staged_names = {x["name"] for x in report["staged_files"]}
    report["counts"] = {
        "cameras_active": len(cam_ids),
        "live_files": len(live_names),
        "staged_files": len(staged_names),
        "sqlite_refs": len(refs),
    }
    for name in sorted(live_names):
        if name not in refs:
            report["orphan_live_candidates"].append(name)
    for name in sorted(staged_names):
        # staged never stored as secret_ref — always "candidate" unless pending outbox
        report["orphan_staged_candidates"].append(name)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        c = report["counts"]
        print(
            f"cameras={c['cameras_active']} live_files={c['live_files']} "
            f"staged_files={c['staged_files']} sqlite_refs={c['sqlite_refs']} "
            f"pending_outbox={report['pending_outbox_count']}"
        )
        print(f"orphan_live_candidates={len(report['orphan_live_candidates'])}")
        print(f"orphan_staged_candidates={len(report['orphan_staged_candidates'])} (may be in-flight)")
        print("READ_ONLY — no deletions performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
