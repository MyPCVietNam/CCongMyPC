"""Synthetic in-memory test. No real secrets, camera, DataDir or network."""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.api.cameras import CameraUpdate, update_camera
from app.core.database import Base
from app.core.utc_time import utc_now
from app.models.entities import CameraDevice, CameraLiveBinding, CameraLabRun, PilotEvidenceRecord
from app.services.camera_trust_lifecycle import classify_camera_update
from app.services.camera_credential_service import CredentialApplyResult, apply_camera_credentials
from app.services.pilot_approval import issue_approval, verify_active_approval

PINS={"model_hash_pin":"synthetic-model", "gallery_revision_pin":"synthetic-gallery", "threshold_id_pin":"synthetic-threshold"}
KEY="test-only-key"; CID_HOST="192.168.0.211"

class FakeSecrets:
    def put_camera_secret(self, camera_id, username, password):
        self.calls.append((camera_id,username,password))
        return f"camera-{camera_id}.bin"
    def has_secret(self, ref): return bool(ref)
    def get_camera_secret(self, ref):
        return {"username":"admin", "password":"synthetic-old"}
    def __init__(self): self.calls=[]


def test_helper_keep_with_password_replaces_credentials():
    secrets=FakeSecrets()
    out=apply_camera_credentials(secrets, camera_id=1, current_secret_ref="camera-1.bin",current_username_hint="admin", action="keep",username="admin",password="synthetic-new",db=None)
    assert out.changed is True and secrets.calls == [(1,"admin","synthetic-new")]
    print("CONFIRMED: keep + nonempty password changes effective credential")


def test_patch_implicit_password_replacement_must_invalidate_hmac():
    e=create_engine("sqlite:///:memory:"); Base.metadata.create_all(e)
    now=utc_now()
    with Session(e) as db:
        cam=CameraDevice(name="Synthetic",host=CID_HOST,rtsp_url_override=f"rtsp://{CID_HOST}:554/ch1/main", config_revision="test-old-rev",created_at=now,enabled=True,mock_mode=False,archived=False,username_hint="admin",secret_ref="camera-1.bin")
        db.add(cam);db.flush();cid=cam.id
        db.add(CameraLiveBinding(camera_id=cid,config_revision="test-old-rev",enabled=True,host=CID_HOST,port=554,path="/ch1/main"))
        db.add(CameraLabRun(run_id="test-run",nonce="test-nonce",kind="CAMERA_LAB",camera_id=cid,state="PHYSICAL_VERIFIED",revoked=False,config_revision="test-old-rev",provenance="CAMERA_LIVE",decoded_w=640,decoded_h=360,started_at=now,expires_at=now+timedelta(hours=7), **PINS))
        db.add(PilotEvidenceRecord(evidence_id="test-ev",kind="CAMERA_LAB",evidence_class="PHYSICAL_VERIFIED",camera_id=cid,lab_run_id="test-run",config_revision="test-old-rev",provenance="CAMERA_LIVE",operator="test",created_at=now,payload_json="{}",**PINS))
        issue_approval(db,secret_key=KEY,kind="CAMERA_LAB",camera_id=cid,issued_by="test",evidence_id="test-ev",**PINS)
        db.commit()
        before=verify_active_approval(db,secret_key=KEY,kind="CAMERA_LAB",camera_id=cid,**PINS)
        assert before and before.valid
        plan=classify_camera_update(row=cam,proposed_host=None,proposed_rtsp=None,proposed_model=None,proposed_firmware=None,proposed_mock=None,proposed_enabled=None,credential_action="keep")
        print("PRE-APPLY classification",plan)
        assert not plan.is_material, "Repro precondition changed; review test"
        fake_result=CredentialApplyResult(secret_ref="camera-1.bin",username_hint="admin",changed=True,action="keep",staged_ref="synthetic-stage")
        with patch("app.api.cameras.apply_camera_credentials",return_value=fake_result):
            out=update_camera(cid,CameraUpdate(password="synthetic-new",credential_action="keep"),db,SimpleNamespace(camera_registry=None,secrets=FakeSecrets()),SimpleNamespace(username="test"))
        db.commit()
        after=verify_active_approval(db,secret_key=KEY,kind="CAMERA_LAB",camera_id=cid,**PINS)
        print("API PATCH material=",out['trust_lifecycle']['material'],"rev=",cam.config_revision,"HMAC active after replacement=",bool(after and after.valid))
        assert after is None, "SECURITY REGRESSION: credential replacement kept old approval valid"
    e.dispose()

def test_helper_keep_with_username_change_reencrypts_credentials():
    secrets=FakeSecrets()
    out=apply_camera_credentials(secrets, camera_id=1, current_secret_ref="camera-1.bin",current_username_hint="admin", action="keep",username="operator2",password="",db=None)
    assert out.changed and out.action=="keep" and secrets.calls==[(1,"operator2","synthetic-old")]
    print("CONFIRMED: keep + new username re-encrypts secret with old password")
