"""P01.5-HF security: no plaintext embeddings; synthetic denied in production."""

from __future__ import annotations

import base64
import json

import cv2
import numpy as np
from sqlalchemy import select

from app.core.settings import AppSettings
from app.main import create_app
from app.models.biometric import EnrollmentSample, EnrollmentSession
from app.services.progress_sanitize import progress_contains_forbidden
from fastapi.testclient import TestClient
from app.core.clock import FrozenClock, local_wall
from app.core.permissions import DEMO_MOCK_INGEST, ENROLLMENT_MANAGE
from app.models.entities import User


def _b64_canvas(salt: int) -> str:
    rng = np.random.default_rng(salt)
    img = np.full((640, 640, 3), 130, dtype=np.uint8)
    img[40:600, 160:480] = rng.integers(80, 190, size=(560, 320, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return base64.b64encode(buf.tobytes()).decode()


def _login(client):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "TestAdminPass!234"})
    assert r.status_code == 200
    return r.json()["csrf_token"]


def test_progress_json_has_no_embeddings_after_face_capture(app_client):
    client, app = app_client
    csrf = _login(client)
    headers = {"X-CSRF-Token": csrf}
    emp = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"code": "NV-HF1", "full_name": "Bảo Mật Embedding"},
    ).json()
    start = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/auto/start",
        headers=headers,
        json={
            "authorization_ref": "HF-1",
            "authorization_ack_vi": "Tôi xác nhận đã thông báo và được phép đăng ký khuôn mặt.",
            "source": "DEMO",
        },
    ).json()
    assert start["source"] == "DEMO"
    assert start.get("capture_origin") == "SYNTHETIC_TEST"
    sid = start["session_id"]
    r = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/auto/{sid}/frame",
        headers=headers,
        json={
            "identity_fixture_key": "NV-HF1",
            "image_base64": _b64_canvas(11),
            "force_slot": "FACE_FRONT",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] is True

    with app.state.container.session_factory() as db:
        row = db.scalar(select(EnrollmentSession).where(EnrollmentSession.public_id == sid))
        assert row is not None
        findings = progress_contains_forbidden(row.progress_json)
        assert findings == [], findings
        data = json.loads(row.progress_json)
        assert "face_embeddings" not in data
        # encrypted sample exists
        samp = db.scalar(
            select(EnrollmentSample).where(
                EnrollmentSample.session_id == row.id,
                EnrollmentSample.slot == "FACE_FRONT",
            )
        )
        assert samp is not None
        assert samp.encrypted_embedding is not None and len(samp.encrypted_embedding) > 16


def test_body_sample_stores_encrypted_image_in_demo(app_client):
    client, app = app_client
    csrf = _login(client)
    headers = {"X-CSRF-Token": csrf}
    emp = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"code": "NV-BODY", "full_name": "Body Enc"},
    ).json()
    start = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/auto/start",
        headers=headers,
        json={
            "authorization_ref": "B",
            "authorization_ack_vi": "Xác nhận đủ dài cho kiểm thử.",
            "source": "DEMO",
        },
    ).json()
    sid = start["session_id"]
    # complete faces quickly
    for i, slot in enumerate(["FACE_FRONT", "FACE_LEFT", "FACE_RIGHT"]):
        assert client.post(
            f"/api/v1/employees/{emp['id']}/enrollment/auto/{sid}/frame",
            headers=headers,
            json={"identity_fixture_key": "NV-BODY", "image_base64": _b64_canvas(20 + i), "force_slot": slot},
        ).json()["accepted"]
    body = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/auto/{sid}/frame",
        headers=headers,
        json={
            "identity_fixture_key": "NV-BODY",
            "image_base64": _b64_canvas(30),
            "force_slot": "BODY_FRONT",
        },
    ).json()
    assert body["accepted"] is True, body
    assert body.get("has_encrypted_image") is True
    sample_uid = body["sample_uid"]
    img = client.get(
        f"/api/v1/employees/{emp['id']}/enrollment/auto/{sid}/samples/{sample_uid}/image",
        headers=headers,
    )
    assert img.status_code == 200
    assert len(img.content) > 100
    assert img.headers.get("cache-control") == "no-store"

    with app.state.container.session_factory() as db:
        samp = db.scalar(select(EnrollmentSample).where(EnrollmentSample.sample_uid == sample_uid))
        assert samp.encrypted_image is not None
        assert samp.image_nonce is not None
        # plaintext JPEG magic must not sit in ciphertext equality with raw
        assert not samp.encrypted_image.startswith(b"\xff\xd8\xff")


def test_production_rejects_fixture_key(tmp_path, frozen_clock):
    settings = AppSettings(
        data_dir=tmp_path / "pdata",
        models_dir=tmp_path / "pmodels",
        secret_key="test-secret-key-32-bytes-minimum!!",
        bootstrap_username="admin",
        bootstrap_password="TestAdminPass!234",
        require_password_change=False,
        app_env="production",
        demo_mode=False,
        allow_mock_observation=False,
        allow_synthetic_fixtures=False,
        allow_force_slot=False,
        database_url=f"sqlite:///{(tmp_path / 'prod.sqlite3').resolve()}",
    )
    application = create_app(settings=settings, clock=frozen_clock)
    with application.state.container.session_factory() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        admin.permissions_json = json.dumps([DEMO_MOCK_INGEST, ENROLLMENT_MANAGE])
        admin.must_change_password = False
        session.commit()
    with TestClient(application) as client:
        csrf = _login(client)
        headers = {"X-CSRF-Token": csrf}
        emp = client.post(
            "/api/v1/employees",
            headers=headers,
            json={"code": "NV-PROD", "full_name": "Prod Deny"},
        ).json()
        # UPLOAD start allowed; fixtures on frame denied
        start = client.post(
            f"/api/v1/employees/{emp['id']}/enrollment/auto/start",
            headers=headers,
            json={
                "authorization_ref": "P",
                "authorization_ack_vi": "Xác nhận đủ dài cho kiểm thử.",
                "source": "UPLOAD",
            },
        )
        assert start.status_code == 200, start.text
        sid = start.json()["session_id"]
        assert start.json()["capture_origin"] == "AUTHORIZED_UPLOAD"
        r = client.post(
            f"/api/v1/employees/{emp['id']}/enrollment/auto/{sid}/frame",
            headers=headers,
            json={"identity_fixture_key": "NV-PROD", "force_slot": "FACE_FRONT", "image_base64": _b64_canvas(1)},
        )
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "SYNTHETIC_FIXTURE_DENIED"


def test_demo_not_remapped_to_auto(app_client):
    client, _ = app_client
    csrf = _login(client)
    headers = {"X-CSRF-Token": csrf}
    emp = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"code": "NV-PROV", "full_name": "Provenance"},
    ).json()
    start = client.post(
        f"/api/v1/employees/{emp['id']}/enrollment/auto/start",
        headers=headers,
        json={
            "authorization_ref": "P",
            "authorization_ack_vi": "Xác nhận đủ dài cho kiểm thử.",
            "source": "DEMO",
        },
    ).json()
    assert start["source"] == "DEMO"
    assert start["capture_origin"] == "SYNTHETIC_TEST"
