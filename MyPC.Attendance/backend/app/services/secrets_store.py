"""Local encrypted secret storage for camera credentials — never log plaintext."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet


def _restrict_windows_acl(path: Path) -> None:
    if sys.platform != "win32":
        return
    try:
        import subprocess

        user = os.environ.get("USERNAME") or os.getlogin()
        subprocess.run(
            ["icacls", str(path), "/inheritance:r"],
            check=False,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["icacls", str(path), "/grant:r", f"{user}:(R,W)"],
            check=False,
            capture_output=True,
            text=True,
        )
        for principal in ("Everyone", "Users", "Authenticated Users", "BUILTIN\\Users"):
            subprocess.run(
                ["icacls", str(path), "/remove", principal],
                check=False,
                capture_output=True,
                text=True,
            )
    except Exception:  # noqa: BLE001
        pass


class SecretsStore:
    def __init__(self, data_dir: Path, master_key: bytes | None = None) -> None:
        self._dir = data_dir / "secrets"
        self._dir.mkdir(parents=True, exist_ok=True)
        key_path = self._dir / "master.key"
        if master_key is not None:
            self._fernet = Fernet(master_key)
        elif key_path.exists():
            self._fernet = Fernet(key_path.read_bytes())
        else:
            key = Fernet.generate_key()
            key_path.write_bytes(key)
            try:
                os.chmod(key_path, 0o600)
            except OSError:
                pass
            _restrict_windows_acl(key_path)
            self._fernet = Fernet(key)
        try:
            os.chmod(self._dir, 0o700)
        except OSError:
            pass
        _restrict_windows_acl(self._dir)

    def put_camera_secret(self, camera_id: int, username: str, password: str) -> str:
        payload = json.dumps({"username": username, "password": password}).encode()
        token = self._fernet.encrypt(payload)
        ref = f"camera-{camera_id}.bin"
        path = self._dir / ref
        path.write_bytes(token)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        _restrict_windows_acl(path)
        return ref

    def get_camera_secret(self, secret_ref: str) -> dict[str, str] | None:
        path = self._dir / secret_ref
        if not path.exists():
            return None
        data = json.loads(self._fernet.decrypt(path.read_bytes()).decode())
        return {"username": data["username"], "password": data["password"]}

    def peek_username(self, secret_ref: str) -> str | None:
        data = self.get_camera_secret(secret_ref)
        if not data:
            return None
        return data.get("username") or None

    def has_secret(self, secret_ref: str) -> bool:
        return bool(secret_ref) and (self._dir / secret_ref).exists()

    def delete_camera_secret(self, secret_ref: str) -> None:
        if not secret_ref:
            return
        # Never delete master.key via this path
        if secret_ref in {"master.key", "session.secret"} or ".." in secret_ref or "/" in secret_ref:
            raise ValueError("ref không hợp lệ")
        path = self._dir / secret_ref
        if not path.exists():
            return
        try:
            size = path.stat().st_size
            with path.open("wb") as f:
                f.write(b"\0" * max(size, 1))
                f.flush()
                os.fsync(f.fileno())
            path.unlink(missing_ok=True)
        except OSError:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
