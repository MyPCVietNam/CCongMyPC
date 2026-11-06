"""P02-USB: source-type / USB identity material changes revoke prior trust; ROI does not."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.core.utc_time import utc_now
from app.models.entities import (
    CameraDevice,
    CameraLabRun,
    CameraLiveBinding,
    PilotApprovalRecord,
    PilotEvidenceRecord,
)
from app.services.camera_trust_lifecycle import (
    classify_camera_update,
    classify_usb_bind_change,
    device_endpoint_identity,
)
from app.services.pilot_approval import issue_approval, verify_active_approval
from app.vision.camera.usb_device import fingerprint_stable_id

PINS = {
    "model_hash_pin": "synthetic-model-pin",
    "gallery_revision_pin": "synthetic-gallery-revision",
    "threshold_id_pin": "synthetic-threshold-pin",
}
KEY = "synthetic-not-for-production-approval-key"


@pytest.fixture
def db_cam():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = utc_now()
    with Session(engine) as db:
        cam = CameraDevice(
            name="EZVIZ synth",
            host="192.168.0.211",
            rtsp_url_override="rtsp://192.168.0.211:554/ch1/main",
            created_at=now,
            archived=False,
            enabled=True,
            mock_mode=False,
            config_revision="revision-A",
            source_type="RTSP",
        )
        db.add(cam)
        db.flush()
        db.add(
            CameraLiveBinding(
                camera_id=cam.id,
                config_revision="revision-A",
                enabled=True,
                host="192.168.0.211",
                port=554,
                path="/ch1/main",
                scheme="rtsp",
            )
        )
        db.add(
            CameraLabRun(
                run_id="run-rtsp",
                nonce="nonce-rtsp",
                kind="CAMERA_LAB",
                camera_id=cam.id,
                state="PHYSICAL_VERIFIED",
                revoked=False,
                config_revision="revision-A",
                provenance="CAMERA_LIVE",
                decoded_w=1920,
                decoded_h=1080,
                fps_measured=20.0,
                owner_reviewed_by="synthetic-owner",
                owner_reviewed_at=now,
                started_at=now,
                expires_at=now + timedelta(hours=7),
                **PINS,
            )
        )
        db.add(
            PilotEvidenceRecord(
                evidence_id="ev-rtsp",
                kind="CAMERA_LAB",
                evidence_class="PHYSICAL_VERIFIED",
                camera_id=cam.id,
                lab_run_id="run-rtsp",
                config_revision="revision-A",
                provenance="CAMERA_LIVE",
                decoded_w=1920,
                decoded_h=1080,
                fps_measured=20.0,
                operator="synthetic-owner",
                created_at=now,
                payload_json="{}",
                **PINS,
            )
        )
        db.flush()
        issue_approval(
            db,
            secret_key=KEY,
            kind="CAMERA_LAB",
            camera_id=cam.id,
            issued_by="synthetic-owner",
            evidence_id="ev-rtsp",
            **PINS,
        )
        db.commit()
        yield db, cam.id
    engine.dispose()


def test_usb_bind_change_is_material(db_cam):
    db, cid = db_cam
    row = db.get(CameraDevice, cid)
    sid = fingerprint_stable_id("USB\\VID_TEST&PID_0001\\A")
    plan = classify_usb_bind_change(row=row, stable_id=sid)
    assert plan.is_material
    assert "source_type" in plan.reasons
    assert plan.revoke_trust is True


def test_same_usb_rebind_not_material():
    sid = fingerprint_stable_id("USB\\VID_TEST&PID_0001\\A")
    row = CameraDevice(
        name="u",
        host="",
        created_at=utc_now(),
        source_type="USB_UVC",
        usb_stable_id=sid,
    )
    plan = classify_usb_bind_change(row=row, stable_id=sid)
    assert not plan.is_material


def test_name_only_not_material(db_cam):
    db, cid = db_cam
    row = db.get(CameraDevice, cid)
    plan = classify_camera_update(
        row=row,
        proposed_host=None,
        proposed_rtsp=None,
        proposed_model=None,
        proposed_firmware=None,
        proposed_mock=None,
        proposed_enabled=None,
        credential_action="keep",
        proposed_source_type=None,
        proposed_usb_stable_id=None,
    )
    assert not plan.is_material


def test_source_type_patch_material(db_cam):
    db, cid = db_cam
    row = db.get(CameraDevice, cid)
    plan = classify_camera_update(
        row=row,
        proposed_host=None,
        proposed_rtsp=None,
        proposed_model=None,
        proposed_firmware=None,
        proposed_mock=None,
        proposed_enabled=None,
        credential_action="keep",
        proposed_source_type="USB_UVC",
        proposed_usb_stable_id=None,
    )
    assert plan.is_material
    assert "source_type" in plan.reasons


def test_usb_endpoint_identity_distinct_from_rtsp(db_cam):
    db, cid = db_cam
    row = db.get(CameraDevice, cid)
    rtsp_id = device_endpoint_identity(row)
    assert rtsp_id["source_type"] == "RTSP"
    row.source_type = "USB_UVC"
    row.usb_stable_id = fingerprint_stable_id("USB\\X")
    usb_id = device_endpoint_identity(row)
    assert usb_id["source_type"] == "USB_UVC"
    assert usb_id["scheme"] == "uvc"
    assert usb_id["usb_stable_id"].startswith("uvc:")


def test_apply_usb_invalidation_revokes_hmac(db_cam):
    from types import SimpleNamespace

    from app.services.camera_trust_lifecycle import apply_material_trust_invalidation

    db, cid = db_cam
    row = db.get(CameraDevice, cid)
    before = verify_active_approval(
        db, secret_key=KEY, kind="CAMERA_LAB", camera_id=cid, **PINS
    )
    assert before is not None and before.valid
    sid = fingerprint_stable_id("USB\\VID_UGREEN\\1")
    plan = classify_usb_bind_change(row=row, stable_id=sid)
    state = SimpleNamespace(camera_registry=None)
    meta = apply_material_trust_invalidation(
        db, row=row, state=state, plan=plan, actor="test"
    )
    db.commit()
    assert meta["material"] is True
    after = verify_active_approval(
        db, secret_key=KEY, kind="CAMERA_LAB", camera_id=cid, **PINS
    )
    assert after is None or not after.valid
    from sqlalchemy import select

    # Historical audit row remains (not silently deleted)
    ev = db.scalar(select(PilotEvidenceRecord).where(PilotEvidenceRecord.evidence_id == "ev-rtsp"))
    assert ev is not None
    appr = db.scalar(select(PilotApprovalRecord).limit(1))
    assert appr is not None
    assert bool(appr.revoked) is True
