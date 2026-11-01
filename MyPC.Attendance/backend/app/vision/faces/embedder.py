"""SFace embedder — REAL path uses alignCrop + feature; synthetic only under explicit fixture mode."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.vision.faces.types import InferenceMode


class EmbeddingError(RuntimeError):
    def __init__(self, message_vi: str, code: str = "EMBEDDING_FAILED") -> None:
        super().__init__(message_vi)
        self.message_vi = message_vi
        self.code = code


@dataclass
class EmbedderInfo:
    model_id: str
    model_hash: str
    backend: str  # opencv_dnn | synthetic_fixture | unavailable
    ready: bool
    inference_mode: str = InferenceMode.SYNTHETIC_FIXTURE.value


class FaceEmbedder:
    """
    Production path: OpenCV Zoo SFace ONNX via cv2.FaceRecognizerSF.alignCrop + feature.
    CI/demo path: deterministic synthetic embedding ONLY when InferenceMode.SYNTHETIC_FIXTURE
    and identity_fixture_key / explicit synthetic backend. Real images NEVER use byte-hash vectors.
    """

    VECTOR_DIM = 128

    def __init__(
        self,
        model_path: Path | None,
        expected_sha256: str | None = None,
        *,
        require_real: bool = False,
    ) -> None:
        self._path = model_path
        self._expected = (expected_sha256 or "").lower()
        self._require_real = require_real
        self._net = None
        self.info = EmbedderInfo(
            model_id="sface_2021dec",
            model_hash="PENDING",
            backend="unavailable",
            ready=False,
            inference_mode=InferenceMode.REAL.value if require_real else InferenceMode.SYNTHETIC_FIXTURE.value,
        )
        self._try_load()

    def _try_load(self) -> None:
        if self._path is None or not self._path.exists():
            if self._require_real:
                self.info = EmbedderInfo(
                    model_id="sface_2021dec",
                    model_hash="MISSING",
                    backend="unavailable",
                    ready=False,
                    inference_mode=InferenceMode.REAL.value,
                )
                return
            self.info = EmbedderInfo(
                model_id="synthetic_fixture_v1",
                model_hash="SYNTHETIC",
                backend="synthetic_fixture",
                ready=True,
                inference_mode=InferenceMode.SYNTHETIC_FIXTURE.value,
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
                inference_mode=InferenceMode.REAL.value,
            )
        except Exception:
            if self._require_real:
                self.info = EmbedderInfo(
                    model_id="sface_2021dec",
                    model_hash=digest,
                    backend="unavailable",
                    ready=False,
                    inference_mode=InferenceMode.REAL.value,
                )
                return
            self.info = EmbedderInfo(
                model_id="sface_2021dec",
                model_hash=digest,
                backend="synthetic_fixture",
                ready=True,
                inference_mode=InferenceMode.SYNTHETIC_FIXTURE.value,
            )

    def align_crop(self, original_bgr: np.ndarray, yunet_row: np.ndarray) -> np.ndarray:
        """Create SFace-aligned crop from original frame + YuNet detection row."""
        if self._net is None:
            raise EmbeddingError(
                "SFace chưa sẵn sàng — không thể căn chỉnh khuôn mặt.",
                "MODEL_UNAVAILABLE",
            )
        if yunet_row is None or np.asarray(yunet_row).size < 15:
            raise EmbeddingError(
                "Thiếu landmark YuNet đầy đủ để căn chỉnh SFace.",
                "LANDMARKS_MISSING",
            )
        try:
            face_row = np.asarray(yunet_row, dtype=np.float32).reshape(1, -1)
            aligned = self._net.alignCrop(original_bgr, face_row)
        except Exception as exc:
            raise EmbeddingError(
                "Căn chỉnh khuôn mặt (alignCrop) thất bại.",
                "ALIGN_FAILED",
            ) from exc
        if aligned is None or getattr(aligned, "size", 0) == 0:
            raise EmbeddingError("alignCrop trả về ảnh rỗng.", "ALIGN_EMPTY")
        return aligned

    def feature_from_aligned(self, aligned_crop: np.ndarray) -> np.ndarray:
        if self._net is None:
            raise EmbeddingError(
                "SFace chưa sẵn sàng — không thể trích xuất đặc trưng.",
                "MODEL_UNAVAILABLE",
            )
        try:
            feat = self._net.feature(aligned_crop)
        except Exception as exc:
            raise EmbeddingError(
                "Trích xuất đặc trưng SFace thất bại.",
                "FEATURE_FAILED",
            ) from exc
        vec = np.asarray(feat, dtype=np.float32).reshape(-1)
        if vec.size == 0 or not np.all(np.isfinite(vec)):
            raise EmbeddingError(
                "Vector đặc trưng không hợp lệ (rỗng hoặc không hữu hạn).",
                "FEATURE_INVALID",
            )
        return _l2_normalize(vec)

    def embed_real(self, original_bgr: np.ndarray, yunet_row: np.ndarray) -> np.ndarray:
        """Production path: alignCrop(original, yunet_row) → feature → L2 normalize."""
        if self._net is None or self.info.backend != "opencv_dnn":
            raise EmbeddingError(
                "Model SFace thật chưa sẵn sàng. Từ chối đăng ký/xác minh thật.",
                "NOT_READY",
            )
        aligned = self.align_crop(original_bgr, yunet_row)
        return self.feature_from_aligned(aligned)

    def embed(
        self,
        bgr_or_rgb_bytes: bytes,
        aligned_crop: np.ndarray | None = None,
        *,
        allow_synthetic_bytes: bool = False,
    ) -> np.ndarray:
        """
        Legacy helper. REAL production must use embed_real().
        Synthetic byte-seeded vectors only when allow_synthetic_bytes=True (fixture tests).
        """
        if self._net is not None and aligned_crop is not None:
            return self.feature_from_aligned(aligned_crop)
        if not allow_synthetic_bytes:
            raise EmbeddingError(
                "Không cho phép nhúng ảnh thật bằng vector synthetic. Cần alignCrop + feature.",
                "SYNTHETIC_FALLBACK_FORBIDDEN",
            )
        if self.info.backend != "synthetic_fixture":
            raise EmbeddingError(
                "Backend không phải synthetic_fixture — từ chối hash-embedding.",
                "SYNTHETIC_FALLBACK_FORBIDDEN",
            )
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
