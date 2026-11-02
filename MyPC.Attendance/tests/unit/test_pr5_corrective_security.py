"""PR5 corrective P0 security regressions — UNIT_SYNTHETIC."""

from __future__ import annotations

import socket

import numpy as np
import pytest

from app.core.secret_bootstrap import (
    KNOWN_WEAK_SECRETS,
    WeakSecretError,
    is_weak_secret,
    load_or_create_session_secret,
    sign_approval_payload,
    verify_approval_signature,
)
from app.core.security import issue_session_token, load_session_token
from app.core.validation import ValidationErrorVi, validate_camera_host
from app.vision.camera.dns_guard import resolve_and_validate_host
from app.vision.camera.gateway import MockFrameGateway
from app.vision.camera.rtsp_policy import validate_live_rtsp_uri


def test_historic_default_secret_is_weak():
    assert is_weak_secret("dev-only-change-me-in-production-32b")
    assert "dev-only-change-me-in-production-32b" in KNOWN_WEAK_SECRETS


def test_production_rejects_weak_env_secret(tmp_path):
    with pytest.raises(WeakSecretError):
        load_or_create_session_secret(
            tmp_path,
            env_value="dev-only-change-me-in-production-32b",
            app_env="production",
            demo_mode=False,
        )


def test_persistent_secret_survives_restart(tmp_path):
    a = load_or_create_session_secret(
        tmp_path, env_value=None, app_env="production", demo_mode=False
    )
    b = load_or_create_session_secret(
        tmp_path, env_value=None, app_env="production", demo_mode=False
    )
    assert a == b
    assert not is_weak_secret(a)
    assert (tmp_path / "secrets" / "session.secret").exists()


def test_forged_session_with_historic_default_fails_against_strong_key():
    forged = issue_session_token(
        "dev-only-change-me-in-production-32b",
        {"uid": 1, "sid": "x", "username": "admin"},
    )
    assert load_session_token("unit-test-csprng-secret-key-not-for-production-use-9f3a", forged, 3600) is None


def test_validation_error_vi_not_swallowed_for_public_ip():
    with pytest.raises(ValidationErrorVi):
        validate_camera_host("8.8.8.8", allow_empty=False)


def test_dns_rebind_blocked():
    def fake_resolver(host, _port, **_kwargs):
        # Pretend LAN hostname resolves to public IP
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 0))]

    with pytest.raises(ValidationErrorVi):
        resolve_and_validate_host("cam-office", resolver=fake_resolver)


def test_rtsp_hostname_uses_dns_guard():
    def fake_resolver(host, _port, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.50", 0))]

    ep = validate_live_rtsp_uri("rtsp://cam-office:554/stream", dns_resolver=fake_resolver)
    assert ep.resolved_ips == ("192.168.1.50",)


def test_bytes_backed_frame_rejects_write_and_setflags():
    gw = MockFrameGateway(camera_id="1", width=32, height=24)
    gw.start()
    fr = gw.get_latest_frame()
    assert fr is not None
    before = fr.pixel_sha256
    view = fr.bgr
    with pytest.raises(ValueError):
        view[0, 0, 0] = 255
    # setflags(write=True) must not enable mutation of underlying bytes storage
    with pytest.raises((ValueError, Exception)):
        view.setflags(write=True)
        view[0, 0, 0] = 123
    assert fr.pixel_sha256 == before
    clone = fr.clone_pixels()
    clone[:] = 9
    assert fr.pixel_sha256 == before
    gw.stop()


def test_approval_hmac_roundtrip():
    secret = "unit-test-csprng-secret-key-not-for-production-use-9f3a"
    payload = '{"approval_id":"a","kind":"AUTO_VALIDATED"}'
    sig = sign_approval_payload(secret, payload)
    assert verify_approval_signature(secret, payload, sig)
    assert not verify_approval_signature(secret, payload, "deadbeef")
