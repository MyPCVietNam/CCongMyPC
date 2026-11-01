"""
REAL-model SFace tests — labeled separately from synthetic fixtures.

Requires OpenCV FaceRecognizerSF + YuNet/SFace ONNX weights under models/weights.
Skips cleanly when weights are absent (CI without binaries).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
WEIGHTS = ROOT / "models" / "weights"
YUNET = WEIGHTS / "face_detection_yunet_2023mar.onnx"
SFACE = WEIGHTS / "face_recognition_sface_2021dec.onnx"
YUNET_SHA = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
SFACE_SHA = "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"

pytestmark = pytest.mark.real_model


def _weights_ready() -> bool:
    if not (YUNET.exists() and SFACE.exists()):
        return False
    try:
        import cv2  # noqa: F401

        return hasattr(cv2, "FaceRecognizerSF") and hasattr(cv2, "FaceDetectorYN")
    except Exception:
        return False


require_weights = pytest.mark.skipif(
    not _weights_ready(),
    reason="REAL ONNX weights or OpenCV face module unavailable",
)


def _synthetic_face_bgr(seed: int = 1, size: int = 480) -> np.ndarray:
    """Draw a crude face-like pattern so YuNet has a chance to fire; not a real person photo."""
    rng = np.random.default_rng(seed)
    img = np.full((size, size, 3), 30, dtype=np.uint8)
    # skin-ish oval region
    cy, cx = size // 2, size // 2
    for y in range(size):
        for x in range(size):
            if ((x - cx) / (size * 0.22)) ** 2 + ((y - cy) / (size * 0.28)) ** 2 <= 1.0:
                img[y, x] = (180, 150, 130)
    # eyes / mouth blobs
    cv = __import__("cv2")
    cv.circle(img, (cx - 35, cy - 20), 8, (20, 20, 20), -1)
    cv.circle(img, (cx + 35, cy - 20), 8, (20, 20, 20), -1)
    cv.ellipse(img, (cx, cy + 40), (25, 10), 0, 0, 360, (40, 40, 80), -1)
    noise = rng.integers(0, 12, size=(size, size, 3), dtype=np.uint8)
    img = cv.add(img, noise)
    return img


@require_weights
def test_model_hashes_match_manifest():
    assert hashlib.sha256(YUNET.read_bytes()).hexdigest() == YUNET_SHA
    assert hashlib.sha256(SFACE.read_bytes()).hexdigest() == SFACE_SHA


def _yunet_row_for_center(size: int = 480) -> np.ndarray:
    """Hand-built YuNet row (bbox + 5 landmarks + score) in native image coords."""
    fw = fh = 160
    x = y = (size - fw) // 2
    re = (x + fw * 0.35, y + fh * 0.38)
    le = (x + fw * 0.65, y + fh * 0.38)
    nose = (x + fw * 0.50, y + fh * 0.55)
    rm = (x + fw * 0.38, y + fh * 0.72)
    lm = (x + fw * 0.62, y + fh * 0.72)
    return np.array(
        [x, y, fw, fh, re[0], re[1], le[0], le[1], nose[0], nose[1], rm[0], rm[1], lm[0], lm[1], 0.99],
        dtype=np.float32,
    )


@require_weights
def test_real_aligncrop_feature_path_not_byte_hash():
    from app.vision.faces.embedder import EmbeddingError, FaceEmbedder
    from app.vision.faces.pipeline import FacePipeline, FacePipelineConfig

    pipe = FacePipeline(FacePipelineConfig(models_dir=WEIGHTS, require_real=True))
    assert pipe.embedder.info.backend == "opencv_dnn"
    assert pipe.detector.info.backend == "opencv_dnn"

    img_a = _synthetic_face_bgr(seed=7)
    img_b = _synthetic_face_bgr(seed=99)
    row_a = _yunet_row_for_center()
    row_b = _yunet_row_for_center()

    # Direct production path: alignCrop(original, yunet_row) → feature()
    vec_a = pipe.embedder.embed_real(img_a, row_a)
    vec_b = pipe.embedder.embed_real(img_b, row_b)
    assert vec_a.shape[0] >= 128
    assert np.all(np.isfinite(vec_a))
    assert abs(float(np.linalg.norm(vec_a)) - 1.0) < 1e-3

    # Must NEVER equal deterministic hash of raw bytes
    synth = FaceEmbedder(None)
    hash_vec = synth.embed(img_a.tobytes(), allow_synthetic_bytes=True)
    assert not np.allclose(vec_a, hash_vec, atol=1e-3)
    # Different images → different SFace vectors (proves real inference, not constant)
    assert not np.allclose(vec_a, vec_b, atol=1e-6)

    with pytest.raises(EmbeddingError):
        pipe.embedder.embed(img_a.tobytes(), aligned_crop=None, allow_synthetic_bytes=False)


@require_weights
def test_missing_landmarks_fail_closed():
    from app.vision.faces.embedder import EmbeddingError, FaceEmbedder

    emb = FaceEmbedder(SFACE, SFACE_SHA, require_real=True)
    img = _synthetic_face_bgr()
    with pytest.raises(EmbeddingError) as ei:
        emb.embed_real(img, np.array([1, 2, 3, 4], dtype=np.float32))
    assert ei.value.code in {"LANDMARKS_MISSING", "ALIGN_FAILED"}


@require_weights
def test_corrupt_hash_rejected():
    from app.vision.faces.embedder import FaceEmbedder

    with pytest.raises(ValueError, match="SHA256"):
        FaceEmbedder(SFACE, "0" * 64, require_real=True)
