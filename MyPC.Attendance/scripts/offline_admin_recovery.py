#!/usr/bin/env python3
"""OWNER-only OFFLINE admin password recovery — no HTTP, no DB wipe.

Usage (interactive; never pass passwords on argv/env):
  python scripts/offline_admin_recovery.py --data-dir /path/to/data

Safety:
  - App must be stopped (exclusive SQLite lock)
  - Explicit typed confirmation
  - Encrypted backup before mutation
  - auth_epoch bump + session revoke + must_change_password=true
  - Never deletes employees / attendance / embeddings
  - Never prints old/new passwords
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Allow running from repo root
ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def _encrypt_backup(src: Path, dest: Path, passphrase: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import secrets

    key = hashlib.sha256(passphrase).digest()
    nonce = secrets.token_bytes(12)
    aes = AESGCM(key)
    plaintext = src.read_bytes()
    ct = aes.encrypt(nonce, plaintext, b"mypc-admin-recovery-v1")
    dest.write_bytes(nonce + ct)
    return hashlib.sha256(plaintext).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline MyPC admin recovery (OWNER local maintenance only)"
    )
    parser.add_argument(
        "--data-dir",
        required=True,
        help="Exact MYPC data directory containing mypc_attendance.sqlite3",
    )
    parser.add_argument(
        "--username",
        default="admin",
        help="Admin username to recover (default: admin)",
    )
    parser.add_argument(
        "--reason",
        default="",
        help="Short recovery reason for audit (no secrets)",
    )
    parser.add_argument(
        "--yes-i-understand",
        action="store_true",
        help="Required confirmation flag in addition to interactive phrase",
    )
    args = parser.parse_args(argv)

    if not args.yes_i_understand:
        _die("Refuse: pass --yes-i-understand after reading SECURE recovery docs.")

    data_dir = Path(args.data_dir).expanduser().resolve()
    db_path = data_dir / "mypc_attendance.sqlite3"
    if not db_path.is_file():
        _die(f"SQLite not found under data-dir (looked for {db_path.name}).")

    # Detect other common profiles — warn, do not merge
    other_hints = []
    for env_key, rel in (
        ("LOCALAPPDATA", Path("MyPC/Attendance/data")),
        ("ProgramData", Path("MyPC/Attendance/data")),
    ):
        base = os.environ.get(env_key) or os.environ.get(env_key.upper())
        # ProgramData on Windows; on Linux skip
        if not base:
            continue
        cand = Path(base) / rel
        if cand.resolve() != data_dir and (cand / "mypc_attendance.sqlite3").exists():
            other_hints.append(str(cand))
    if other_hints:
        print("WARNING: additional data profiles detected (not modified):")
        for h in other_hints:
            print(f"  - {h}")
        print("Recovery applies ONLY to --data-dir above.")

    confirm = input(
        'Type exactly RECOVER-ADMIN-PASSWORD to continue (app must be STOPPED): '
    ).strip()
    if confirm != "RECOVER-ADMIN-PASSWORD":
        _die("Aborted — confirmation phrase mismatch.")

    new_password = getpass.getpass("New admin password (≥10 chars, not echoed): ")
    confirm_pw = getpass.getpass("Confirm new admin password: ")
    if new_password != confirm_pw:
        _die("Passwords do not match.")
    if len(new_password) < 10:
        _die("Password too short (min 10).")

    backup_pass = getpass.getpass(
        "Backup encryption passphrase (≥12 chars; store offline): "
    )
    if len(backup_pass) < 12:
        _die("Backup passphrase too short.")

    reason = (args.reason or "").strip() or "owner_offline_recovery"
    if any(x in reason.lower() for x in ("password", "secret", "token")):
        _die("Reason must not contain secret-like words; keep it non-sensitive.")

    from sqlalchemy import create_engine, event, select, text
    from sqlalchemy.orm import Session, sessionmaker

    from app.core.security import hash_password
    from app.models.entities import AuditLog, AuthSession, User
    from app.services.auth_session_service import bump_auth_epoch, revoke_all_user_sessions
    from app.core.utc_time import utc_now

    from sqlalchemy.pool import NullPool

    url = f"sqlite:///{db_path}"
    # NullPool — do not hold connections across recovery steps
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 5},
        poolclass=NullPool,
    )

    @event.listens_for(engine, "connect")
    def _set_locks(dbapi_conn, _):  # type: ignore[no-untyped-def]
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    # Exclusive lock — fail if another writer holds the DB
    import sqlite3

    try:
        raw = sqlite3.connect(str(db_path), timeout=5.0, isolation_level=None)
        try:
            raw.execute("BEGIN EXCLUSIVE")
            raw.execute("SELECT 1 FROM users LIMIT 1")
            raw.execute("COMMIT")
        finally:
            raw.close()
    except Exception as exc:  # noqa: BLE001
        _die(f"Cannot lock database exclusively (is the app still running?): {type(exc).__name__}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = data_dir / "recovery_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"mypc_attendance.pre_recovery.{stamp}.sqlite3.aes"
    try:
        plain_sha = _encrypt_backup(db_path, backup_path, backup_pass.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        _die(f"Backup failed — aborting before any change: {type(exc).__name__}")

    meta = {
        "schema": "mypc.admin-recovery.v1",
        "utc": stamp,
        "data_dir": str(data_dir),
        "backup_file": backup_path.name,
        "plaintext_sha256": plain_sha,
        "username": args.username,
        "reason": reason,
        "operator": os.environ.get("USERNAME") or os.environ.get("USER") or "unknown",
        "secrets_redacted": True,
    }
    (backup_dir / f"recovery_meta.{stamp}.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    try:
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.username == args.username, User.active.is_(True)))
            if user is None:
                _die(f"Active user '{args.username}' not found — no mutation.")
            user.password_hash = hash_password(new_password)
            user.must_change_password = True
            epoch = bump_auth_epoch(db, user)
            revoked = revoke_all_user_sessions(db, user_id=user.id, reason="OFFLINE_RECOVERY")
            # Ensure auth_sessions table exists on older DBs
            _ = AuthSession
            db.add(
                AuditLog(
                    actor=meta["operator"],
                    action="OFFLINE_ADMIN_RECOVERY",
                    entity_type="user",
                    entity_id=str(user.id),
                    before_checksum="",
                    after_checksum=f"auth_epoch={epoch}",
                    reason=f"{reason}; sessions_revoked={revoked}; backup={backup_path.name}",
                    timestamp=utc_now(),
                    request_id=stamp,
                )
            )
            db.commit()
    except Exception as exc:  # noqa: BLE001
        # Attempt restore from encrypted backup is manual with passphrase —
        # we did not truncate the live DB on failure of commit.
        _die(f"Recovery transaction failed; live DB unchanged if commit aborted: {type(exc).__name__}")

    # Clear secrets from locals
    new_password = ""
    confirm_pw = ""
    backup_pass = ""
    print("OK: admin password rotated; sessions invalidated; must_change_password=true.")
    print(f"Encrypted backup: {backup_path.name}")
    print("Start the app and complete forced password change in the browser.")
    print("Employees / attendance / embeddings were NOT deleted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
