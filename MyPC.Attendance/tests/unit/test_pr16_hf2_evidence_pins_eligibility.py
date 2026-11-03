"""PR16-HF2: pins=None ⇒ eligible_for_sign=False."""

from __future__ import annotations

from app.core.utc_time import utc_now
from app.models.entities import CameraDevice, PilotEvidenceRecord
from app.services.evidence_store import (
    EVIDENCE_PHYSICAL,
    KIND_CAMERA_LAB,
    list_physical_evidence_for_camera,
)


def test_pins_none_not_eligible(app_client):
    _client, app = app_client
    with app.state.container.session_factory() as db:
        cam = CameraDevice(
            name="PinCam",
            host="192.168.0.230",
            mock_mode=False,
            connection_status="CONFIG_SAVED",
            created_at=utc_now(),
        )
        db.add(cam)
        db.flush()
        db.add(
            PilotEvidenceRecord(
                evidence_id="ev-pins-none",
                kind=KIND_CAMERA_LAB,
                evidence_class=EVIDENCE_PHYSICAL,
                camera_id=cam.id,
                lab_run_id="lab-1",
                provenance="CAMERA_LIVE",
                decoded_w=100,
                decoded_h=100,
                fps_measured=10.0,
                model_hash_pin="m",
                gallery_revision_pin="g",
                threshold_id_pin="t",
                operator="admin",
                created_at=utc_now(),
                payload_json="{}",
            )
        )
        db.commit()
        cid = cam.id
        items = list_physical_evidence_for_camera(db, camera_id=cid, kind=KIND_CAMERA_LAB, pins=None)
        assert items
        assert items[0]["eligible_for_sign"] is False
        assert items[0]["eligible_reason"] == "SERVER_PINS_UNAVAILABLE"
        assert items[0]["pin_status"] == "PINS_UNAVAILABLE"

        items_ok = list_physical_evidence_for_camera(
            db,
            camera_id=cid,
            kind=KIND_CAMERA_LAB,
            pins={
                "model_hash_pin": "m",
                "gallery_revision_pin": "g",
                "threshold_id_pin": "t",
            },
        )
        assert items_ok[0]["eligible_for_sign"] is True
        assert items_ok[0]["eligible_reason"] == "OK"
