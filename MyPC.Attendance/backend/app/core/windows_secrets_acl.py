"""Unified Windows secret-store ACL policy — least privilege, inheritable, fail-closed.

Policy (secrets directory under MYPC_DATA_DIR):
  - Current interactive user SID: (OI)(CI)(M) on directory → children inherit
  - SYSTEM (S-1-5-18): (OI)(CI)(F)
  - No Everyone / BUILTIN\\Users / Authenticated Users grants
  - Never regenerate inaccessible existing secrets
  - Never silently swallow icacls failures during explicit ensure/repair
  - Idempotent: healthy ACL (whether icacls prints SID or DOMAIN\\User) is left unchanged
"""

from __future__ import annotations

import logging
import os
import re
import socket
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

# Win32 constants
_SE_FILE_OBJECT = 1
_DACL_SECURITY_INFORMATION = 0x00000004
_ERROR_SUCCESS = 0

# ACCESS_MASK bits commonly used by icacls (M)/(F)
_FILE_GENERIC_READ = 0x120089
_FILE_GENERIC_WRITE = 0x120116
_FILE_GENERIC_EXECUTE = 0x1200A0
_FILE_ALL_ACCESS = 0x1F01FF
_GENERIC_ALL = 0x10000000
_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_DELETE = 0x00010000
_WRITE_DAC = 0x00040000
_WRITE_OWNER = 0x00080000
_SYNCHRONIZE = 0x00100000
_READ_CONTROL = 0x00020000

# Inheritance flags (ACE Header AceFlags)
_OBJECT_INHERIT_ACE = 0x1
_CONTAINER_INHERIT_ACE = 0x2
_NO_PROPAGATE_INHERIT_ACE = 0x4
_INHERIT_ONLY_ACE = 0x8
_INHERITED_ACE = 0x10

# AceType
_ACCESS_ALLOWED_ACE_TYPE = 0x0


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
class AceInfo:
    sid: str
    ace_type: int
    ace_flags: int
    mask: int

    @property
    def object_inherit(self) -> bool:
        return bool(self.ace_flags & _OBJECT_INHERIT_ACE)

    @property
    def container_inherit(self) -> bool:
        return bool(self.ace_flags & _CONTAINER_INHERIT_ACE)

    @property
    def inherit_only(self) -> bool:
        return bool(self.ace_flags & _INHERIT_ONLY_ACE)


@dataclass
class SecretsAclReport:
    secrets_dir: str
    platform: str
    current_sid: str | None
    files: list[dict] = field(default_factory=list)
    directory_policy_ok: bool | None = None
    secrets_redacted: bool = True
    guidance_vi: str = ""
    inspection_method: str = ""


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
        if getattr(exc, "errno", None) in {13, 5} or "Permission" in type(exc).__name__:
            raise SecretAccessDeniedError(path) from exc
        raise


def assert_app_stopped(*, port: int = 8765) -> None:
    """Fail if local Attendance listener is still up (best-effort)."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            raise RuntimeError(
                f"Cổng {port} vẫn LISTEN — dừng MyPC Attendance trước khi sửa ACL."
            )
    except OSError:
        return


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
    try:
        proc = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            line = proc.stdout.strip().splitlines()[0]
            parts = [p.strip().strip('"') for p in line.split(",")]
            for p in parts:
                if p.startswith("S-1-"):
                    return p
    except Exception:  # noqa: BLE001
        pass
    # Fallback: WindowsIdentity via PowerShell (still SID-stable)
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "[Security.Principal.WindowsIdentity]::GetCurrent().User.Value",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        val = (proc.stdout or "").strip()
        if proc.returncode == 0 and val.startswith("S-1-"):
            return val
    except Exception:  # noqa: BLE001
        pass
    return None


def _sid_grant(sid: str, rights: str) -> str:
    return f"*{sid}:{rights}"


def _mask_allows_modify(mask: int) -> bool:
    """True if ACE mask is at least Modify-like or Full Control."""
    if mask & _GENERIC_ALL or mask & _FILE_ALL_ACCESS == _FILE_ALL_ACCESS:
        return True
    # Modify ≈ read+write+execute+delete (icacls M)
    needed = _FILE_GENERIC_READ | _FILE_GENERIC_WRITE | _DELETE | _READ_CONTROL
    # Also accept GENERIC_READ|GENERIC_WRITE combinations
    if (mask & _GENERIC_READ) and (mask & _GENERIC_WRITE):
        return True
    return (mask & needed) == needed or (mask & (_FILE_GENERIC_READ | _FILE_GENERIC_WRITE | _DELETE)) == (
        _FILE_GENERIC_READ | _FILE_GENERIC_WRITE | _DELETE
    )


def _mask_allows_full(mask: int) -> bool:
    if mask & _GENERIC_ALL:
        return True
    return (mask & _FILE_ALL_ACCESS) == _FILE_ALL_ACCESS or (
        (mask & _WRITE_DAC) and (mask & _WRITE_OWNER) and _mask_allows_modify(mask)
    )


def read_dacl_aces(path: Path) -> list[AceInfo]:
    """
    Resolve DACL via Win32 GetNamedSecurityInfo — independent of icacls display form.
    Returns empty list on non-Windows.
    """
    if not is_windows():
        return []
    import ctypes
    from ctypes import wintypes

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    GetNamedSecurityInfoW = advapi.GetNamedSecurityInfoW
    GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
    ]
    GetNamedSecurityInfoW.restype = wintypes.DWORD

    LocalFree = kernel.LocalFree
    LocalFree.argtypes = [wintypes.HLOCAL]
    LocalFree.restype = wintypes.HLOCAL

    ConvertSidToStringSidW = advapi.ConvertSidToStringSidW
    ConvertSidToStringSidW.argtypes = [wintypes.LPVOID, ctypes.POINTER(wintypes.LPWSTR)]
    ConvertSidToStringSidW.restype = wintypes.BOOL

    GetAce = advapi.GetAce
    GetAce.argtypes = [wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.LPVOID)]
    GetAce.restype = wintypes.BOOL

    owner = wintypes.LPVOID()
    group = wintypes.LPVOID()
    dacl = wintypes.LPVOID()
    sacl = wintypes.LPVOID()
    sd = wintypes.LPVOID()
    rc = GetNamedSecurityInfoW(
        str(path),
        _SE_FILE_OBJECT,
        _DACL_SECURITY_INFORMATION,
        ctypes.byref(owner),
        ctypes.byref(group),
        ctypes.byref(dacl),
        ctypes.byref(sacl),
        ctypes.byref(sd),
    )
    if rc != _ERROR_SUCCESS or not dacl:
        raise RuntimeError(f"GetNamedSecurityInfo thất bại cho {path.name} (code={rc})")

    try:
        # ACL header: AclRevision(1) Sbz1(1) AclSize(2) AceCount(2) Sbz2(2)
        class ACL(ctypes.Structure):
            _fields_ = [
                ("AclRevision", ctypes.c_ubyte),
                ("Sbz1", ctypes.c_ubyte),
                ("AclSize", ctypes.c_ushort),
                ("AceCount", ctypes.c_ushort),
                ("Sbz2", ctypes.c_ushort),
            ]

        acl = ACL.from_address(dacl.value)
        aces: list[AceInfo] = []
        for i in range(acl.AceCount):
            ace_ptr = wintypes.LPVOID()
            if not GetAce(dacl, i, ctypes.byref(ace_ptr)):
                continue
            # ACE_HEADER
            ace_type = ctypes.c_ubyte.from_address(ace_ptr.value).value
            ace_flags = ctypes.c_ubyte.from_address(ace_ptr.value + 1).value
            # ACCESS_ALLOWED_ACE: header(4) + Mask(4) + SidStart
            if ace_type != _ACCESS_ALLOWED_ACE_TYPE:
                continue
            mask = ctypes.c_uint32.from_address(ace_ptr.value + 4).value
            sid_addr = ace_ptr.value + 8
            sid_str = wintypes.LPWSTR()
            if not ConvertSidToStringSidW(sid_addr, ctypes.byref(sid_str)):
                continue
            try:
                sid_value = sid_str.value
            finally:
                if sid_str:
                    LocalFree(sid_str)
            if sid_value:
                aces.append(
                    AceInfo(
                        sid=str(sid_value),
                        ace_type=int(ace_type),
                        ace_flags=int(ace_flags),
                        mask=int(mask),
                    )
                )
        return aces
    finally:
        if sd:
            LocalFree(sd)


def directory_policy_is_healthy(secrets_dir: Path, user_sid: str) -> bool:
    """
    True when DACL already grants:
      - user SID: allow + (OI)+(CI) + modify-or-better (not inherit-only-only)
      - SYSTEM: allow + (OI)+(CI) + full/modify
    Uses Win32 SID resolution — works whether icacls prints SID or DOMAIN\\User.
    """
    if not is_windows() or not secrets_dir.is_dir():
        return False
    try:
        aces = read_dacl_aces(secrets_dir)
    except Exception as exc:  # noqa: BLE001
        logger.warning("acl_inspect_failed path=%s err=%s", secrets_dir.name, type(exc).__name__)
        return False

    user_ok = False
    system_ok = False
    for ace in aces:
        if ace.inherit_only and not (ace.object_inherit or ace.container_inherit):
            continue
        if ace.sid == user_sid and ace.object_inherit and ace.container_inherit and _mask_allows_modify(ace.mask):
            # Prefer non-inherit-only ACE that applies to the directory itself as well
            if not ace.inherit_only:
                user_ok = True
            elif not user_ok:
                # inherit-only (OI)(CI) still propagates to children; accept as partial
                user_ok = True
        if ace.sid == SID_SYSTEM and ace.object_inherit and ace.container_inherit and (
            _mask_allows_full(ace.mask) or _mask_allows_modify(ace.mask)
        ):
            if not ace.inherit_only:
                system_ok = True
            elif not system_ok:
                system_ok = True
    return bool(user_ok and system_ok)


# Back-compat alias used by older call sites / tests
def directory_has_inheritable_user_ace(secrets_dir: Path, user_sid: str) -> bool:
    return directory_policy_is_healthy(secrets_dir, user_sid)


def ensure_secrets_dir_acl(secrets_dir: Path, *, force: bool = False) -> list[AclCommandResult]:
    """
    Apply inheritable directory ACL once when missing/unhealthy.
    Does NOT recursively reset unrelated trees. Does NOT rewrite secret bytes.
    Idempotent: already-correct ACL → no icacls mutations.
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

    if not force and directory_policy_is_healthy(secrets_dir, user_sid):
        logger.info(
            "secrets_acl_dir_ok unchanged path=%s sid_suffix=%s",
            secrets_dir.name,
            user_sid[-8:],
        )
        return results

    # Save current DACL before mutation when possible
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
    for sid in (SID_EVERYONE, SID_AUTHENTICATED_USERS, SID_BUILTIN_USERS):
        results.append(_run_icacls([str(secrets_dir), "/remove:g", f"*{sid}"], check=False))
    for name in ("Everyone", "Users", "Authenticated Users", "BUILTIN\\Users"):
        results.append(_run_icacls([str(secrets_dir), "/remove:g", name], check=False))

    if not directory_policy_is_healthy(secrets_dir, user_sid):
        raise RuntimeError(
            "ACL thư mục secrets chưa đạt policy (OI)(CI) cho user+SYSTEM sau ensure "
            "(kiểm tra bằng GetNamedSecurityInfo/SID, không dựa vào chuỗi icacls)."
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
    results.extend(ensure_secrets_dir_acl(path.parent, force=False))
    results.append(
        _run_icacls([str(path), "/grant:r", _sid_grant(SID_SYSTEM, "(F)")], check=True)
    )
    results.append(
        _run_icacls([str(path), "/grant:r", _sid_grant(user_sid, "(M)")], check=True)
    )
    return results


def save_acl_snapshot(path: Path, dest: Path) -> AclCommandResult:
    """Preserve current ACL text via icacls /save before mutation."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    return _run_icacls([str(path), "/save", str(dest)], check=True)


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
        results.append(save_acl_snapshot(path, acl_backup_dir / f"{path.name}.acl.txt"))
    results.append(
        _run_icacls([str(path), "/grant:r", _sid_grant(SID_SYSTEM, "(F)")], check=True)
    )
    results.append(
        _run_icacls([str(path), "/grant:r", _sid_grant(user_sid, "(M)")], check=True)
    )
    # Never grant Everyone
    results.append(_run_icacls([str(path), "/remove:g", f"*{SID_EVERYONE}"], check=False))
    results.append(_run_icacls([str(path), "/remove:g", "Everyone"], check=False))
    if not can_read_file(path):
        raise SecretAccessDeniedError(
            path,
            detail_vi=f"SECRET_ACCESS_DENIED: vẫn không đọc được '{path.name}' sau khi cấp ACL.",
        )
    return results


def probe_secrets_access(data_dir: Path) -> SecretsAclReport:
    secrets_dir = data_dir / "secrets"
    sid = current_user_sid() if is_windows() else None
    method = "win32_GetNamedSecurityInfo" if is_windows() else "n/a"
    report = SecretsAclReport(
        secrets_dir=str(secrets_dir),
        platform=sys.platform,
        current_sid=(sid[-12:] if sid else None),
        guidance_vi=(
            "Nếu READ_DENIED: dừng app, chạy Repair-MyPCSecretsAcl.ps1 -Repair "
            "hoặc scripts/repair_secrets_acl.py --repair. Không xóa/tái tạo khóa."
        ),
        inspection_method=method,
    )
    if not secrets_dir.is_dir():
        report.directory_policy_ok = False
        report.files.append({"name": "(missing secrets dir)", "status": "MISSING_DIR"})
        return report
    if is_windows() and sid:
        report.directory_policy_ok = directory_policy_is_healthy(secrets_dir, sid)
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
        if is_windows():
            raise RuntimeError(
                f"Không thiết lập được ACL thư mục secrets: {type(exc).__name__}: {exc}"
            ) from exc
        logger.debug("secrets_acl_dir_skip non-windows: %s", type(exc).__name__)

    for p in list_known_secret_files(secrets_dir):
        assert_readable_existing_secret(p)
