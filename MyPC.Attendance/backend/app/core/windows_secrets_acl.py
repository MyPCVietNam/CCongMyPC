"""Unified Windows secret-store ACL policy — least privilege, inheritable, fail-closed.

Policy (secrets directory under MYPC_DATA_DIR):
  - Current interactive user SID: (OI)(CI)(M) on directory → children inherit
  - SYSTEM (S-1-5-18): (OI)(CI)(F)
  - No Everyone / BUILTIN\\Users / Authenticated Users grants
  - Never regenerate inaccessible existing secrets
  - Never silently swallow icacls failures during explicit ensure/repair
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("mypc.secrets_acl")

KNOWN_SECRET_NAMES = frozenset(
    {
        "session.secret",
        "master.key",
        "face_templates.key",
    }
)
CAMERA_SECRET_RE = re.compile(r"^camera-\d+\.bin$")

# Well-known SIDs
SID_SYSTEM = "S-1-5-18"
SID_EVERYONE = "S-1-1-0"
SID_AUTHENTICATED_USERS = "S-1-5-11"
SID_BUILTIN_USERS = "S-1-5-32-545"


class SecretAccessDeniedError(PermissionError):
    """Existing secret file is present but unreadable — never regenerate."""

    code = "SECRET_ACCESS_DENIED"

    def __init__(self, path: Path, *, detail_vi: str | None = None) -> None:
        self.path = path
        self.filename = path.name
        msg = detail_vi or (
            f"SECRET_ACCESS_DENIED: không đọc được '{path.name}' dù tệp tồn tại. "
            "Không tái tạo khóa. Chạy scripts/windows/Repair-MyPCSecretsAcl.ps1 "
            "hoặc `python scripts/repair_secrets_acl.py --data-dir <MYPC_DATA_DIR> --repair` "
            "(app phải dừng). Giữ nguyên SQLite và nội dung khóa."
        )
        super().__init__(msg)


@dataclass
class AclCommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class SecretsAclReport:
    secrets_dir: str
    platform: str
    current_sid: str | None
    files: list[dict] = field(default_factory=list)
    directory_policy_ok: bool | None = None
    secrets_redacted: bool = True
    guidance_vi: str = ""


def is_windows() -> bool:
    return sys.platform == "win32"


def is_known_secret_name(name: str) -> bool:
    return name in KNOWN_SECRET_NAMES or bool(CAMERA_SECRET_RE.match(name))


def list_known_secret_files(secrets_dir: Path) -> list[Path]:
    if not secrets_dir.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(secrets_dir.iterdir()):
        if p.is_file() and not p.is_symlink() and is_known_secret_name(p.name):
            out.append(p)
    return out


def can_read_file(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            f.read(1)
        return True
    except OSError:
        return False


def assert_readable_existing_secret(path: Path) -> None:
    """Fail closed when a secret file exists but cannot be read — never treat as missing."""
    if not path.exists():
        return
    if path.is_symlink():
        raise SecretAccessDeniedError(path, detail_vi=f"SECRET_ACCESS_DENIED: '{path.name}' là symlink — từ chối.")
    try:
        with path.open("rb") as f:
            f.read(1)
    except PermissionError as exc:
        raise SecretAccessDeniedError(path) from exc
    except OSError as exc:
        # Access denied often surfaces as PermissionError; some platforms use OSError errno 13
        if getattr(exc, "errno", None) in {13, 5} or "Permission" in type(exc).__name__:
            raise SecretAccessDeniedError(path) from exc
        raise


def _run_icacls(args: list[str], *, check: bool) -> AclCommandResult:
    argv = ["icacls", *args]
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("icacls không khả dụng trên hệ thống này") from exc
    result = AclCommandResult(
        argv=argv,
        returncode=int(proc.returncode),
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
    )
    if check and not result.ok:
        raise RuntimeError(
            f"icacls thất bại (exit {result.returncode}): {' '.join(argv[1:3])}… "
            f"{(result.stderr or result.stdout)[:200]}"
        )
    return result


def current_user_sid() -> str | None:
    if not is_windows():
        return None
    # Prefer whoami /user — stable SID without depending on USERNAME string
    try:
        proc = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            # "domain\user","S-1-5-21-..."
            line = proc.stdout.strip().splitlines()[0]
            parts = [p.strip().strip('"') for p in line.split(",")]
            for p in parts:
                if p.startswith("S-1-"):
                    return p
    except Exception:  # noqa: BLE001
        pass
    try:
        import ctypes
        from ctypes import wintypes

        # Fallback via GetUserNameEx is heavy; use environment for diagnostics only
        _ = ctypes  # silence unused on non-win path analyzers
        _ = wintypes
    except Exception:  # noqa: BLE001
        pass
    return None


def _sid_grant(sid: str, rights: str) -> str:
    # icacls SID form: *S-1-5-21-...:(OI)(CI)(M)
    return f"*{sid}:{rights}"


def directory_has_inheritable_user_ace(secrets_dir: Path, user_sid: str) -> bool:
    """Heuristic: icacls output mentions user SID with (OI)(CI)."""
    if not is_windows() or not secrets_dir.is_dir():
        return False
    result = _run_icacls([str(secrets_dir)], check=False)
    text = (result.stdout or "") + (result.stderr or "")
    if user_sid not in text:
        return False
    # Accept either (OI)(CI) or (CI)(OI) ordering near the SID line
    for line in text.splitlines():
        if user_sid in line and "(OI)" in line and "(CI)" in line:
            return True
    return False


def ensure_secrets_dir_acl(secrets_dir: Path, *, force: bool = False) -> list[AclCommandResult]:
    """
    Apply inheritable directory ACL once when missing/unhealthy.
    Does NOT recursively reset unrelated trees. Does NOT rewrite secret bytes.
    """
    results: list[AclCommandResult] = []
    secrets_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(secrets_dir, 0o700)
    except OSError:
        pass
    if not is_windows():
        return results

    user_sid = current_user_sid()
    if not user_sid:
        raise RuntimeError("Không lấy được SID người dùng Windows — từ chối đặt ACL bí mật.")

    if not force and directory_has_inheritable_user_ace(secrets_dir, user_sid):
        logger.info(
            "secrets_acl_dir_ok path=%s sid_suffix=%s",
            secrets_dir.name,
            user_sid[-8:],
        )
        return results

    # Disable inheritance on the secrets directory only, then grant inheritable ACEs.
    results.append(_run_icacls([str(secrets_dir), "/inheritance:r"], check=True))
    results.append(
        _run_icacls(
            [str(secrets_dir), "/grant:r", _sid_grant(SID_SYSTEM, "(OI)(CI)(F)")],
            check=True,
        )
    )
    results.append(
        _run_icacls(
            [str(secrets_dir), "/grant:r", _sid_grant(user_sid, "(OI)(CI)(M)")],
            check=True,
        )
    )
    # Remove broad principals if present (best-effort but report failures)
    for sid in (SID_EVERYONE, SID_AUTHENTICATED_USERS, SID_BUILTIN_USERS):
        r = _run_icacls([str(secrets_dir), "/remove:g", f"*{sid}"], check=False)
        results.append(r)
        # Also try friendly names
    for name in ("Everyone", "Users", "Authenticated Users", "BUILTIN\\Users"):
        results.append(_run_icacls([str(secrets_dir), "/remove:g", name], check=False))

    if not directory_has_inheritable_user_ace(secrets_dir, user_sid):
        raise RuntimeError(
            "ACL thư mục secrets chưa có ACE (OI)(CI) cho người dùng hiện tại sau ensure."
        )
    return results


def apply_new_secret_file_acl(path: Path) -> list[AclCommandResult]:
    """ACL for a newly created secret file — explicit + rely on parent inheritance."""
    results: list[AclCommandResult] = []
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    if not is_windows():
        return results
    if not is_known_secret_name(path.name):
        raise ValueError(f"không áp ACL cho tên không nằm trong allowlist: {path.name}")
    user_sid = current_user_sid()
    if not user_sid:
        raise RuntimeError("Không lấy được SID người dùng Windows")
    # Ensure parent policy first (idempotent skip if healthy)
    results.extend(ensure_secrets_dir_acl(path.parent, force=False))
    results.append(
        _run_icacls([str(path), "/grant:r", _sid_grant(SID_SYSTEM, "(F)")], check=True)
    )
    results.append(
        _run_icacls([str(path), "/grant:r", _sid_grant(user_sid, "(M)")], check=True)
    )
    return results


def repair_existing_secret_file_acl(
    path: Path,
    *,
    acl_backup_dir: Path | None = None,
) -> list[AclCommandResult]:
    """Owner-authorized scoped grant for one existing unreadable secret — no content change."""
    if not is_windows():
        raise RuntimeError("repair ACL chỉ áp dụng trên Windows")
    if not path.is_file() or path.is_symlink():
        raise RuntimeError(f"Không phải tệp bí mật hợp lệ: {path.name}")
    if not is_known_secret_name(path.name):
        raise RuntimeError(f"Tên tệp không thuộc allowlist: {path.name}")
    user_sid = current_user_sid()
    if not user_sid:
        raise RuntimeError("Không lấy được SID người dùng")
    results: list[AclCommandResult] = []
    if acl_backup_dir is not None:
        acl_backup_dir.mkdir(parents=True, exist_ok=True)
        save_path = acl_backup_dir / f"{path.name}.acl.txt"
        # icacls /save writes a file; path arg is the output file
        results.append(_run_icacls([str(path), "/save", str(save_path)], check=True))
    results.append(
        _run_icacls([str(path), "/grant:r", _sid_grant(SID_SYSTEM, "(F)")], check=True)
    )
    results.append(
        _run_icacls([str(path), "/grant:r", _sid_grant(user_sid, "(M)")], check=True)
    )
    if not can_read_file(path):
        raise SecretAccessDeniedError(
            path,
            detail_vi=f"SECRET_ACCESS_DENIED: vẫn không đọc được '{path.name}' sau khi cấp ACL.",
        )
    return results


def probe_secrets_access(data_dir: Path) -> SecretsAclReport:
    secrets_dir = data_dir / "secrets"
    sid = current_user_sid() if is_windows() else None
    report = SecretsAclReport(
        secrets_dir=str(secrets_dir),
        platform=sys.platform,
        current_sid=(sid[-12:] if sid else None),  # truncated — not a secret
        guidance_vi=(
            "Nếu READ_DENIED: dừng app, chạy Repair-MyPCSecretsAcl.ps1 -Repair "
            "hoặc scripts/repair_secrets_acl.py --repair. Không xóa/tái tạo khóa."
        ),
    )
    if not secrets_dir.is_dir():
        report.directory_policy_ok = False
        report.files.append({"name": "(missing secrets dir)", "status": "MISSING_DIR"})
        return report
    if is_windows() and sid:
        report.directory_policy_ok = directory_has_inheritable_user_ace(secrets_dir, sid)
    else:
        report.directory_policy_ok = True
    for p in list_known_secret_files(secrets_dir):
        status = "READ_PASS" if can_read_file(p) else "READ_DENIED"
        report.files.append(
            {
                "name": p.name,
                "status": status,
                "bytes": p.stat().st_size if status == "READ_PASS" else None,
                "secrets_redacted": True,
            }
        )
    return report


def prepare_secrets_dir_for_app(data_dir: Path) -> None:
    """Called at app start: ensure dir policy; fail closed on unreadable existing secrets."""
    secrets_dir = data_dir / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    try:
        ensure_secrets_dir_acl(secrets_dir, force=False)
    except Exception as exc:  # noqa: BLE001
        # Directory ACL ensure failure on Windows is serious; surface clearly
        if is_windows():
            raise RuntimeError(
                f"Không thiết lập được ACL thư mục secrets: {type(exc).__name__}: {exc}"
            ) from exc
        logger.debug("secrets_acl_dir_skip non-windows: %s", type(exc).__name__)

    for p in list_known_secret_files(secrets_dir):
        assert_readable_existing_secret(p)
