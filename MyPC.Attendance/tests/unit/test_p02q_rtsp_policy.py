"""P02-HF strict RTSP policy — UNIT_SYNTHETIC."""

from __future__ import annotations

import pytest

from app.core.validation import ValidationErrorVi
from app.vision.camera.rtsp_policy import diagnostic_rtsp_label, validate_live_rtsp_uri


def test_valid_private_lan():
    ep = validate_live_rtsp_uri("rtsp://192.168.1.50:554/Streaming/Channels/101")
    assert ep.host == "192.168.1.50"
    assert ep.port == 554
    assert "Streaming" in ep.path
    assert "password" not in ep.diagnostic_label.lower()


@pytest.mark.parametrize(
    "url",
    [
        "rtsp://admin:s3cret@192.168.1.50:554/ch1",
        "rtsp://192.168.1.50:554/ch1?token=abc",
        "rtsp://192.168.1.50:554/ch1#frag",
        "rtsp://192.168.1.50:554/%40secret",
        "http://192.168.1.50/stream",
        "rtsp://127.0.0.1:554/a",
        "rtsp://localhost:554/a",
        "rtsp://169.254.169.254:554/a",
        "rtsp://8.8.8.8:554/a",
        "rtsp://192.168.1.50:9999/ch1",
        "rtsp://192.168.1.50:554/a\n",
        " rtsps://192.168.1.50:554/a",
    ],
)
def test_reject_unsafe_uris(url):
    with pytest.raises(ValidationErrorVi):
        validate_live_rtsp_uri(url)


def test_diagnostic_label_has_no_path():
    label = diagnostic_rtsp_label(camera_id=7, profile="MAIN")
    assert "camera_id=7" in label
    assert "REDACTED" in label
    assert "/" not in label.split("uri=")[-1] or label.endswith("REDACTED")
