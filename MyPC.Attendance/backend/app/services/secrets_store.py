"""Local encrypted secret storage for camera credentials — never log plaintext."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from cryptography.fernet import Fernet

from app.core.windows_secrets_acl import (
    SecretAccessDeniedError,
    apply_new_secret_file_acl,
    assert_readable_existing_secret,
    ensure_secrets_dir_acl,
    prepare_secrets_dir_for_app,
)


class SecretsStore:
    def __init__(self, data_dir: Path, master_key: bytes | None = None) -> None:
        self._dir = data_dir / "secrets"
        prepare_secrets_dir_for_app(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        key_path = self._dir / "master.key"
        if master_key is not None:
            self._fernet = Fernet(master_key)
        elif key_path.exists():
            assert_readable_existing_secret(key_path)
            try:
                self._fernet = Fernet(key_path.read_bytes())
            except PermissionError as exc:
                raise SecretAccessDeniedError(key_path) from exc
        else:
            key = Fernet.generate_key()
            key_path.write_bytes(key)
            try:
                os.chmod(key_path, 0o600)
            except OSError:
                pass
            apply_new_secret_file_acl(key_path)
            self._fernet = Fernet(key)
        try:
            os.chmod(self._dir, 0o700)
        except OSError:
            pass
        # Idempotent: skip destructive reset when inheritable ACL already healthy
        ensure_secrets_dir_acl(self._dir, force=False)

    def live_camera_ref(self, camera_id: int) -> str:
        return f"camera-{int(camera_id)}.bin"

    def _validate_ref(self, secret_ref: str) -> None:
        if not secret_ref:
            raise ValueError("ref trống")
        if secret_ref in {"master.key", "session.secret", "face_templates.key"}:
            raise ValueError("ref không hợp lệ")
        if ".." in secret_ref or "/" in secret_ref or "\\" in secret_ref:
            raise ValueError("ref không hợp lệ")
        # Allow camera-N.bin and camera-N.staged-<uuid>.bin only
        if not secret_ref.startswith("camera-"):
            raise ValueError("ref không hợp lệ")

    def _write_encrypted(self, ref: str, username: str, password: str) -> str:
        self._validate_ref(ref)
        payload = json.dumps({"username": username, "password": password}).encode()
        token = self._fernet.encrypt(payload)
        path = self._dir / ref
        path.write_bytes(token)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        apply_new_secret_file_acl(path)
        return ref

    def put_camera_secret(self, camera_id: int, username: str, password: str) -> str:
        """Immediate live write — prefer stage_camera_secret + promote for transactional paths."""
        return self._write_encrypted(self.live_camera_ref(camera_id), username, password)

    def stage_camera_secret(self, camera_id: int, username: str, password: str) -> str:
        """Write a unique staged blob; does not overwrite the live camera-{id}.bin."""
        token = uuid.uuid4().hex
        ref = f"camera-{int(camera_id)}.staged-{token}.bin"
        return self._write_encrypted(ref, username, password)

    def promote_staged_camera_secret(self, staged_ref: str, live_ref: str) -> None:
        """Atomically replace live credential with staged content after DB commit."""
        self._validate_ref(staged_ref)
        self._validate_ref(live_ref)
        staged = self._dir / staged_ref
        live = self._dir / live_ref
        if not staged.exists():
            raise FileNotFoundError(f"staged secret missing: {staged_ref}")
        # Same-directory replace is atomic on Windows/POSIX for the final name.
        os.replace(staged, live)
        try:
            os.chmod(live, 0o600)
        except OSError:
            pass
        apply_new_secret_file_acl(live)

    def scrub_orphaned_staged_secrets(self) -> int:
        """Crash recovery: remove unreferenced staged blobs left after abrupt stop."""
        n = 0
        for path in self._dir.glob("camera-*.staged-*.bin"):
            try:
                self.delete_camera_secret(path.name)
                n += 1
            except Exception:
                pass
        return n

    def get_camera_secret(self, secret_ref: str) -> dict[str, str] | None:
        if not secret_ref:
            return None
        self._validate_ref(secret_ref)
        path = self._dir / secret_ref
        if not path.exists():
            return None
        assert_readable_existing_secret(path)
        try:
            data = json.loads(self._fernet.decrypt(path.read_bytes()).decode())
        except PermissionError as exc:
            raise SecretAccessDeniedError(path) from exc
        return {"username": data["username"], "password": data["password"]}

    def peek_username(self, secret_ref: str) -> str | None:
        data = self.get_camera_secret(secret_ref)
        if not data:
            return None
        return data.get("username") or None

    def has_secret(self, secret_ref: str) -> bool:
        if not secret_ref:
            return False
        try:
            self._validate_ref(secret_ref)
        except ValueError:
            return False
        return (self._dir / secret_ref).exists()

    def delete_camera_secret(self, secret_ref: str) -> None:
        if not secret_ref:
            return
        self._validate_ref(secret_ref)
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
        except PermissionError as exc:
            raise SecretAccessDeniedError(path) from exc
        except OSError:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
