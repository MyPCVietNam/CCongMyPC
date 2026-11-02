#!/usr/bin/env python3
"""Owner-authorized secrets ACL audit/repair — never rewrite secret bytes or SQLite.

Safeguards before any ACL mutation:
  - Attendance listener must be stopped (port 8765)
  - Critical secrets must exist (allowlist only)
  - Readable critical-secret backups must be present
  - Directory + target-file ACLs are preserved via icacls /save
  - Never regenerate session.secret / master.key / face_templates.key / camera-*.bin / SQLite
  - Never grant Everyone

Usage:
  python scripts/repair_secrets_acl.py --data-dir "$LOCALAPPDATA/MyPC/Attendance/data" --check
  python scripts/repair_secrets_acl.py --data-dir ... --repair --yes-i-understand
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

CRITICAL_NAMES = ("session.secret", "master.key", "face_templates.key")


def _die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_backup_root(data_dir: Path) -> Path:
    # Prefer .../Attendance/backups when data_dir is .../Attendance/data
    sibling = data_dir.parent / "backups"
    if sibling.is_dir():
        return sibling
    nested = data_dir / "backups"
    if nested.is_dir():
        return nested
    _die("Thiếu thư mục backups — dừng; không tái tạo khóa.")
    raise AssertionError  # unreachable


def _resolve_backup_secret(folder: Path, name: str) -> Path | None:
    candidates = [
        folder / "data" / "secrets" / name,
        folder / "secrets" / name,
        folder / name,
    ]
    for p in candidates:
        if p.is_file() and not p.is_symlink():
            return p
    return None


def _find_usable_critical_backup(backup_root: Path) -> Path:
    from app.core.windows_secrets_acl import can_read_file

    folders = sorted(
        (
            p
            for p in backup_root.iterdir()
            if p.is_dir()
            and (
                p.name.startswith("pre-camera-hf-")
                or p.name.startswith("pre-secrets-acl-")
                or p.name.startswith("secrets-content-")
            )
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for folder in folders:
        ok = True
        for name in CRITICAL_NAMES:
            path = _resolve_backup_secret(folder, name)
            if path is None or not can_read_file(path):
                ok = False
                break
        if ok:
            return folder
    _die(
        "Không tìm thấy backup đầy đủ/đọc được cho session.secret + master.key + "
        "face_templates.key. Dừng; không tái tạo khóa."
    )
    raise AssertionError


def _assert_critical_live(secrets_dir: Path) -> None:
    for name in CRITICAL_NAMES:
        path = secrets_dir / name
        if not path.is_file() or path.is_symlink():
            _die(f"Thiếu tệp bí mật quan trọng: {name}. Không tái tạo.")
        if path.stat().st_size == 0:
            _die(f"Tệp bí mật rỗng: {name}. Dừng.")
        if name == "face_templates.key" and path.stat().st_size != 32:
            _die("face_templates.key không đúng 32 bytes. Dừng.")


def _compare_critical_with_backup(secrets_dir: Path, backup: Path) -> None:
    from app.core.windows_secrets_acl import can_read_file

    for name in CRITICAL_NAMES:
        live = secrets_dir / name
        if not can_read_file(live):
            print(f"CHECKSUM_SKIPPED_UNREADABLE: {name}")
            continue
        bak = _resolve_backup_secret(backup, name)
        if bak is None:
            _die(f"Backup thiếu {name}")
        if _sha256(live) != _sha256(bak):
            _die(
                f"Nội dung {name} khác backup — không ghi đè/tái tạo khóa. "
                "Dừng để bảo toàn tính toàn vẹn."
            )
        print(f"CONTENT_MATCHES_BACKUP: {name}")


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
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Attendance listen port that must be stopped before repair",
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
    if secrets_dir.is_symlink():
        _die("secrets là symlink — từ chối.")

    from app.core.windows_secrets_acl import (
        assert_app_stopped,
        can_read_file,
        current_user_sid,
        directory_policy_is_healthy,
        ensure_secrets_dir_acl,
        is_windows,
        list_known_secret_files,
        probe_secrets_access,
        repair_existing_secret_file_acl,
        save_acl_snapshot,
    )

    # Always require app stopped before any ACL path (check is read-only but
    # repair mutations absolutely require this; check also verifies for owner ops).
    try:
        assert_app_stopped(port=int(args.port))
    except RuntimeError as exc:
        _die(str(exc))

    _assert_critical_live(secrets_dir)
    backup_root = _find_backup_root(data_dir)
    backup = _find_usable_critical_backup(backup_root)
    print(f"CRITICAL_PRESTART_BACKUP: FOUND_AND_READABLE ({backup.name})")

    report = probe_secrets_access(data_dir)
    print(json.dumps(report.__dict__, indent=2, ensure_ascii=False, default=str))

    denied = [f for f in report.files if f.get("status") == "READ_DENIED"]
    known = list_known_secret_files(secrets_dir)
    if args.check:
        _compare_critical_with_backup(secrets_dir, backup)
        print(
            f"CHECK_ONLY: {len(denied)} READ_DENIED of {len(report.files)} known secrets. "
            "No ACL changes."
        )
        return 1 if denied else 0

    if not args.yes_i_understand:
        _die("Repair yêu cầu --yes-i-understand sau khi đọc hướng dẫn VI.")
    if not is_windows():
        _die("Repair ACL Windows chỉ chạy trên Windows.")

    confirm = input("Type REPAIR-EXISTING-SECRETS to authorize scoped ACL changes: ").strip()
    if confirm != "REPAIR-EXISTING-SECRETS":
        _die("Cancelled — no ACL changes.")

    user_sid = current_user_sid()
    if not user_sid:
        _die("Không lấy được SID người dùng hiện tại.")

    dir_healthy = directory_policy_is_healthy(secrets_dir, user_sid)
    if not denied and dir_healthy and not args.force_dir_policy:
        _compare_critical_with_backup(secrets_dir, backup)
        print("REPAIR_NOT_NEEDED: ALL_READABLE_AND_DIR_HEALTHY")
        print("IDEMPOTENT: no ACL mutations performed.")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    acl_backup = backup_root / f"secrets-acl-before-{stamp}"
    acl_backup.mkdir(parents=True, exist_ok=True)

    # Preserve directory ACL before any mutation.
    save_acl_snapshot(secrets_dir, acl_backup / "secrets-dir.acl.txt")

    # Directory policy first (idempotent unless force / unhealthy)
    ensure_secrets_dir_acl(secrets_dir, force=bool(args.force_dir_policy))

    repaired: list[str] = []
    for path in known:
        if can_read_file(path):
            print(f"SKIP_READABLE {path.name}")
            continue
        repair_existing_secret_file_acl(path, acl_backup_dir=acl_backup)
        repaired.append(path.name)
        print(f"REPAIRED {path.name}")

    _compare_critical_with_backup(secrets_dir, backup)

    post = probe_secrets_access(data_dir)
    still = [f["name"] for f in post.files if f.get("status") == "READ_DENIED"]
    if still:
        _die(f"Vẫn READ_DENIED sau repair: {', '.join(still)}")
    if not directory_policy_is_healthy(secrets_dir, user_sid):
        _die("Directory policy vẫn chưa đạt (OI)(CI) user+SYSTEM sau repair.")

    print(
        json.dumps(
            {
                "repaired": repaired,
                "acl_backup_dir": str(acl_backup),
                "ok": True,
                "everyone_granted": False,
                "content_rewritten": False,
            },
            indent=2,
        )
    )
    print("EXISTING_SECRETS_RECOVERY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
