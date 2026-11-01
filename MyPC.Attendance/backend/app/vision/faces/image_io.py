"""Fail-closed image decoding for real enrollment/verification paths."""

from __future__ import annotations

import base64
import imghdr
from dataclasses import dataclass

import numpy as np

# Limits
MAX_COMPRESSED_BYTES = 8 * 1024 * 1024  # 8 MiB
MAX_PIXELS = 12_000_000  # ~4000x3000
MAX_DIM = 4096
ALLOWED_FORMATS = {"jpeg", "png"}


class ImageDecodeError(ValueError):
    def __init__(self, message_vi: str, code: str = "INVALID_IMAGE") -> None:
        super().__init__(message_vi)
        self.message_vi = message_vi
        self.code = code


@dataclass(frozen=True)
class DecodedImage:
    bgr: np.ndarray
    format: str
    compressed_bytes: int


def decode_image_base64(
    b64: str | None,
    *,
    allow_empty_for_fixture: bool = False,
) -> DecodedImage:
    """
    Decode JPEG/PNG from base64. Fail closed — never invent a synthetic gray image.
    """
    if not b64:
        if allow_empty_for_fixture:
            raise ImageDecodeError(
                "Thiếu dữ liệu ảnh (fixture phải cung cấp image_base64 hoặc identity_fixture_key).",
                "MISSING_IMAGE",
            )
        raise ImageDecodeError("Thiếu dữ liệu ảnh.", "MISSING_IMAGE")

    try:
        raw = base64.b64decode(b64, validate=False)
    except Exception as exc:
        raise ImageDecodeError("Chuỗi base64 không hợp lệ.", "BAD_BASE64") from exc

    if len(raw) > MAX_COMPRESSED_BYTES:
        raise ImageDecodeError(
            f"Ảnh vượt giới hạn {MAX_COMPRESSED_BYTES // (1024*1024)} MB.",
            "TOO_LARGE",
        )
    if len(raw) < 24:
        raise ImageDecodeError("Tệp ảnh quá nhỏ hoặc hỏng.", "TOO_SMALL")

    kind = imghdr.what(None, h=raw)
    # imghdr may return 'jpeg'/'png'; also check magic
    if kind is None:
        if raw[:3] == b"\xff\xd8\xff":
            kind = "jpeg"
        elif raw[:8] == b"\x89PNG\r\n\x1a\n":
            kind = "png"
    if kind not in ALLOWED_FORMATS:
        raise ImageDecodeError(
            "Chỉ chấp nhận JPEG hoặc PNG.",
            "UNSUPPORTED_FORMAT",
        )

    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise ImageDecodeError(
            "OpenCV chưa sẵn sàng để giải mã ảnh.",
            "OPENCV_MISSING",
        ) from exc

    arr = np.frombuffer(raw, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        raise ImageDecodeError("Không giải mã được ảnh (file hỏng hoặc không hỗ trợ).", "DECODE_FAILED")

    h, w = img.shape[:2]
    if h > MAX_DIM or w > MAX_DIM or (h * w) > MAX_PIXELS:
        raise ImageDecodeError("Kích thước ảnh vượt giới hạn an toàn.", "DIMENSION_LIMIT")

    return DecodedImage(bgr=img, format=kind, compressed_bytes=len(raw))
