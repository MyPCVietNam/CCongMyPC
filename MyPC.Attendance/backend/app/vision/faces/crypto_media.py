"""AES-GCM helpers for biometric vectors and authorized reference images."""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.vision.faces.embedder import packing_floats, unpacking_floats
import numpy as np


class MediaCrypto:
    """Process-local key for templates + enrollment sample blobs."""

    def __init__(self, data_dir: Path, key_filename: str = "face_templates.key") -> None:
        self._dir = data_dir / "secrets"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._key_path = self._dir / key_filename
        self._key = self._load_or_create_key()
        self.key_version = 1

    def _load_or_create_key(self) -> bytes:
        if self._key_path.exists():
            return self._key_path.read_bytes()
        key = AESGCM.generate_key(bit_length=256)
        self._key_path.write_bytes(key)
        try:
            os.chmod(self._key_path, 0o600)
        except OSError:
            pass
        return key

    def encrypt_bytes(self, plain: bytes, aad: bytes) -> tuple[bytes, bytes]:
        aes = AESGCM(self._key)
        nonce = os.urandom(12)
        return aes.encrypt(nonce, plain, aad), nonce

    def decrypt_bytes(self, ciphertext: bytes, nonce: bytes, aad: bytes) -> bytes:
        return AESGCM(self._key).decrypt(nonce, ciphertext, aad)

    def encrypt_embedding(self, vec: np.ndarray, aad: bytes = b"mypc-face-v1") -> tuple[bytes, bytes]:
        return self.encrypt_bytes(packing_floats(vec), aad)

    def decrypt_embedding(self, ciphertext: bytes, nonce: bytes, aad: bytes = b"mypc-face-v1") -> np.ndarray:
        return unpacking_floats(self.decrypt_bytes(ciphertext, nonce, aad))

    def encrypt_image(self, jpeg_or_png: bytes, aad: bytes = b"mypc-body-ref-v1") -> tuple[bytes, bytes]:
        return self.encrypt_bytes(jpeg_or_png, aad)

    def decrypt_image(self, ciphertext: bytes, nonce: bytes, aad: bytes = b"mypc-body-ref-v1") -> bytes:
        return self.decrypt_bytes(ciphertext, nonce, aad)
