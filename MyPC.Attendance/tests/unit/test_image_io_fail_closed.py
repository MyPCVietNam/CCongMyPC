"""Fail-closed image decode — never invent synthetic gray for corrupt uploads."""

from __future__ import annotations

import base64

import pytest

from app.vision.faces.image_io import ImageDecodeError, decode_image_base64


def test_missing_image():
    with pytest.raises(ImageDecodeError) as ei:
        decode_image_base64(None)
    assert ei.value.code == "MISSING_IMAGE"


def test_bad_base64_still_decodes_or_fails_cleanly():
    # base64.b64decode(validate=False) is lenient; garbage may fail at decode
    with pytest.raises(ImageDecodeError):
        decode_image_base64(base64.b64encode(b"not-an-image-!!!!!!!!!!!!!!").decode())


def test_valid_png_roundtrip():
    import cv2
    import numpy as np

    img = np.full((64, 64, 3), 90, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    b64 = base64.b64encode(buf.tobytes()).decode()
    decoded = decode_image_base64(b64)
    assert decoded.format == "png"
    assert decoded.bgr.shape[0] == 64
