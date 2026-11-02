#!/usr/bin/env python3
"""Read-only multi-profile / first-run diagnostic — never prints secrets or hashes."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _profile(name: str, path: Path) -> dict:
    db = path / "mypc_attendance.sqlite3"
    secret = path / "FIRST_RUN_ADMIN.txt"
    return {
        "name": name,
        "path": str(path),
        "dir_exists": path.is_dir(),
        "sqlite_present": db.is_file(),
        "first_run_secret_file_present": secret.is_file(),
        "secrets_redacted": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect MyPC Attendance data profiles")
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="MyPC.Attendance root (for ./data profile)",
    )
    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()
    profiles = [
        _profile("REPO_LOCAL", root / "data"),
    ]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        profiles.append(_profile("LOCALAPPDATA", Path(local) / "MyPC" / "Attendance" / "data"))
    prog = os.environ.get("ProgramData") or os.environ.get("PROGRAMDATA")
    if prog:
        profiles.append(_profile("PROGRAMDATA", Path(prog) / "MyPC" / "Attendance" / "data"))
    explicit = os.environ.get("MYPC_DATA_DIR")
    if explicit:
        profiles.append(_profile("MYPC_DATA_DIR", Path(explicit).expanduser().resolve()))

    present = [p for p in profiles if p["sqlite_present"] or p["first_run_secret_file_present"]]
    report = {
        "schema": "mypc.data-profile-inspect.v1",
        "profiles": profiles,
        "multiple_active_profiles": len(present) > 1,
        "note_vi": (
            "Mỗi hồ sơ dữ liệu có mật khẩu lần đầu riêng. "
            "Không gộp/ghi đè DB. 401 = mật khẩu hiện tại bị từ chối — chưa đổi mật khẩu mới."
        ),
        "secrets_redacted": True,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
