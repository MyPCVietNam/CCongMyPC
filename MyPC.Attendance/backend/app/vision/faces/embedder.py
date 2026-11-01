"""SFace embedder with deterministic synthetic fallback for CI without weights."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class EmbedderInfo:
    model_id: str
    model_hash: str
    backend: str  # opencv_dnn | synthetic_fixture
    ready: bool


class FaceEmbedder:
    """
    Production path: OpenCV Zoo SFace ONNX via cv2.FaceRecognizerSF when available.
    CI/demo path: deterministic synthetic embedding from image bytes (NOT for real identity).
    """

    VECTOR_DIM = 128

    def __init__(self, model_path: Path | None, expected_sha256: str | None = None) -> None:
        self._path = model_path
        self._expected = (expected_sha256 or "").lower()
        self._net = None
        self.info = EmbedderInfo(
            model_id="sface_2021dec",
            model_hash="PENDING",
            backend="synthetic_fixture",
            ready=False,
        )
        self._try_load()

    def _try_load(self) -> None:
        if self._path is None or not self._path.exists():
            self.info = EmbedderInfo(
                model_id="synthetic_fixture_v1",
                model_hash="SYNTHETIC",
                backend="synthetic_fixture",
                ready=True,
            )
            return
        data = self._path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if self._expected and self._expected not in {"", "pending_download_verify"} and digest != self._expected:
            raise ValueError(
                f"SFace model SHA256 mismatch: got {digest}, expected {self._expected}"
            )
        try:
            import cv2  # type: ignore

            recognizer = cv2.FaceRecognizerSF.create(str(self._path), "")
            self._net = recognizer
            self.info = EmbedderInfo(
                model_id="sface_2021dec",
                model_hash=digest,
                backend="opencv_dnn",
                ready=True,
            )
        except Exception:
            # Weights present but OpenCV face module unavailable — keep hash, synthetic runtime
            self.info = EmbedderInfo(
                model_id="sface_2021dec",
                model_hash=digest,
                backend="synthetic_fixture",
                ready=True,
            )

    def embed(self, bgr_or_rgb_bytes: bytes, aligned_crop: np.ndarray | None = None) -> np.ndarray:
        if self._net is not None and aligned_crop is not None:
            import cv2  # type: ignore

            feat = self._net.feature(aligned_crop)
            vec = np.asarray(feat, dtype=np.float32).reshape(-1)
            return _l2_normalize(vec)
        # Deterministic synthetic embedding from bytes — for unit/replay only
        seed = hashlib.sha256(bgr_or_rgb_bytes).digest()
        rng = np.random.default_rng(int.from_bytes(seed[:8], "little"))
        vec = rng.standard_normal(self.VECTOR_DIM).astype(np.float32)
        return _l2_normalize(vec)

    def embed_identity_fixture(self, identity_key: str, quality_noise: float = 0.0) -> np.ndarray:
        """Stable per-identity vector for synthetic tests (not a real biometric)."""
        seed = hashlib.sha256(f"mypc-synth::{identity_key}".encode()).digest()
        rng = np.random.default_rng(int.from_bytes(seed[:8], "little"))
        vec = rng.standard_normal(self.VECTOR_DIM).astype(np.float32)
        if quality_noise:
            vec = vec + rng.standard_normal(self.VECTOR_DIM).astype(np.float32) * quality_noise
        return _l2_normalize(vec)


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(vec))
    if n < 1e-12:
        return vec
    return (vec / n).astype(np.float32)


def packing_floats(vec: np.ndarray) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec.tolist())


def unpacking_floats(data: bytes) -> np.ndarray:
    n = len(data) // 4
    return np.asarray(struct.unpack(f"{n}f", data), dtype=np.float32)
