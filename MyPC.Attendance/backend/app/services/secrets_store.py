"""Local encrypted secret storage for camera credentials — never log plaintext."""

from __future__ import annotations

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet


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
            self._fernet = Fernet(key)

    def put_camera_secret(self, camera_id: int, username: str, password: str) -> str:
        payload = json.dumps({"username": username, "password": password}).encode()
        token = self._fernet.encrypt(payload)
        ref = f"camera-{camera_id}.bin"
        (self._dir / ref).write_bytes(token)
        try:
            os.chmod(self._dir / ref, 0o600)
        except OSError:
            pass
        return ref

    def get_camera_secret(self, secret_ref: str) -> dict[str, str] | None:
        path = self._dir / secret_ref
        if not path.exists():
            return None
        data = json.loads(self._fernet.decrypt(path.read_bytes()).decode())
        return {"username": data["username"], "password": data["password"]}

    def has_secret(self, secret_ref: str) -> bool:
        return bool(secret_ref) and (self._dir / secret_ref).exists()
