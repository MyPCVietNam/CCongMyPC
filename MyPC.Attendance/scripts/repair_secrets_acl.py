#!/usr/bin/env python3
"""Owner-authorized secrets ACL audit/repair — never rewrite secret bytes or SQLite.

Usage:
  python scripts/repair_secrets_acl.py --data-dir "$LOCALAPPDATA/MyPC/Attendance/data" --check
  python scripts/repair_secrets_acl.py --data-dir ... --repair --yes-i-understand
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MyPC secrets ACL audit/repair")
    parser.add_argument("--data-dir", required=True, help="Exact MYPC_DATA_DIR (contains secrets/)")
    parser.add_argument("--check", action="store_true", help="Read-only probe (default)")
    parser.add_argument("--repair", action="store_true", help="Owner-authorized ACL repair")
    parser.add_argument(
        "--yes-i-understand",
        action="store_true",
        help="Required with --repair",
    )
    parser.add_argument(
        "--force-dir-policy",
        action="store_true",
        help="Re-apply inheritable directory ACL even if already healthy",
    )
    args = parser.parse_args(argv)
    if args.repair and args.check:
        _die("Chọn --check hoặc --repair, không cả hai.")
    if not args.repair:
        args.check = True

    data_dir = Path(args.data_dir).expanduser().resolve()
    secrets_dir = data_dir / "secrets"
    if not secrets_dir.is_dir():
        _die("Thiếu thư mục secrets — không tạo khóa mới.")

    from app.core.windows_secrets_acl import (
        ensure_secrets_dir_acl,
        is_windows,
        list_known_secret_files,
        probe_secrets_access,
        repair_existing_secret_file_acl,
    )

    report = probe_secrets_access(data_dir)
    print(json.dumps(report.__dict__, indent=2, ensure_ascii=False, default=str))

    denied = [f for f in report.files if f.get("status") == "READ_DENIED"]
    if args.check:
        print(f"CHECK_ONLY: {len(denied)} READ_DENIED of {len(report.files)} known secrets.")
        return 1 if denied else 0

    if not args.yes_i_understand:
        _die("Repair yêu cầu --yes-i-understand sau khi đọc hướng dẫn VI.")
    if not is_windows():
        _die("Repair ACL Windows chỉ chạy trên Windows.")

    confirm = input("Type REPAIR-EXISTING-SECRETS to authorize scoped ACL changes: ").strip()
    if confirm != "REPAIR-EXISTING-SECRETS":
        _die("Cancelled — no ACL changes.")

    # Ensure inheritable directory policy first (idempotent unless --force-dir-policy)
    ensure_secrets_dir_acl(secrets_dir, force=bool(args.force_dir_policy))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    acl_backup = data_dir.parent / "backups" / f"secrets-acl-before-{stamp}"
    # Prefer sibling backups under Attendance home if data is .../Attendance/data
    if (data_dir.parent / "backups").is_dir() or True:
        acl_backup = data_dir.parent / "backups" / f"secrets-acl-before-{stamp}"

    repaired = []
    for path in list_known_secret_files(secrets_dir):
        from app.core.windows_secrets_acl import can_read_file

        if can_read_file(path):
            print(f"SKIP_READABLE {path.name}")
            continue
        repair_existing_secret_file_acl(path, acl_backup_dir=acl_backup)
        repaired.append(path.name)
        print(f"REPAIRED {path.name}")

    post = probe_secrets_access(data_dir)
    still = [f["name"] for f in post.files if f.get("status") == "READ_DENIED"]
    if still:
        _die(f"Vẫn READ_DENIED sau repair: {', '.join(still)}")
    print(json.dumps({"repaired": repaired, "acl_backup_dir": str(acl_backup), "ok": True}, indent=2))
    print("EXISTING_SECRETS_RECOVERY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
