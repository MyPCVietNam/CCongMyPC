"""Synthetic AB provenance regression. No network, camera, files or real credentials.

This tests *verification* of an already signed AUTO_VALIDATED token if its AB run
no longer exists. The HTTP issuance path currently checks AB at issuance.
"""
from datetime import timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.core.database import Base
from app.core.utc_time import utc_now
from app.models.entities import CameraDevice,CameraLiveBinding,CameraLabRun,PilotEvidenceRecord
from app.services.pilot_approval import issue_approval,verify_active_approval
PINS=dict(model_hash_pin='test-model',gallery_revision_pin='test-gallery',threshold_id_pin='test-threshold')
KEY='synthetic-key-not-production'

def test_auto_validated_must_recheck_ab_backing():
    engine=create_engine('sqlite:///:memory:'); Base.metadata.create_all(engine)
    with Session(engine) as db:
        now=utc_now();cam=CameraDevice(name='Synthetic Camera',host='192.168.0.210',config_revision='test-r1',enabled=True,mock_mode=False,archived=False,created_at=now)
        db.add(cam);db.flush();cid=cam.id
        db.add(CameraLiveBinding(camera_id=cid,enabled=True,config_revision='test-r1',host='192.168.0.210',port=554,path='/ch1/main'))
        for kind in ('CAMERA_LAB','FACE_PILOT'):
            runid='run-'+kind
            evid='ev-'+kind
            db.add(CameraLabRun(run_id=runid,nonce='nonce-'+kind,camera_id=cid,kind=kind,state='PHYSICAL_VERIFIED',config_revision='test-r1',provenance='CAMERA_LIVE',revoked=False,started_at=now,expires_at=now+timedelta(hours=7),**PINS))
            db.add(PilotEvidenceRecord(evidence_id=evid,camera_id=cid,kind=kind,lab_run_id=runid,config_revision='test-r1',provenance='CAMERA_LIVE',evidence_class='PHYSICAL_VERIFIED',operator='test',created_at=now,payload_json='{}',**PINS))
            issue_approval(db,secret_key=KEY,kind=kind,camera_id=cid,issued_by='test',evidence_id=evid,**PINS)
        # This simulates a previously signed AUTO_VALIDATED approval whose backing AB
        # was subsequently deleted/revoked; API issuance normally checks AB.
        issue_approval(db,secret_key=KEY,kind='AUTO_VALIDATED',camera_id=cid,issued_by='test',ab_run_id='AB-run-no-longer-present',**PINS)
        db.commit()
        view=verify_active_approval(db,secret_key=KEY,kind='AUTO_VALIDATED',camera_id=cid,**PINS)
        print('AUTO_VALIDATED with nonexistent AB backing:',bool(view and view.valid))
        assert view is None, 'AUTO_VALIDATED must deny if signed AB run no longer exists'
    engine.dispose()
