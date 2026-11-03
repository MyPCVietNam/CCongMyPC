"""PR13 independent regression gates: synthetic local SQLite/data only.

Copy this file into MyPC.Attendance/tests/ and execute:
  python -m pytest -q tests/test_pr13_independent_regressions.py

These tests assert DESIRED behavior. They intentionally FAIL on PR13 feature commit
6503713e683ee0d31a8c7d37a50a636139b47bf4 until corrected.
Never use owner DataDir or camera passwords; fixtures use temporary files only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.core.database import Base
from app.models.entities import CameraDevice
from app.services.secrets_store import SecretsStore
from app.services.secret_fs_outbox import (
    queue_delete, queue_promote, recover_pending_outbox,
    process_outbox_row, apply_outbox_after_commit,
    abort_outbox_after_rollback, release_session_credential_locks,
)


def _db(tmp_path: Path):
    eng=create_engine(f'sqlite:///{tmp_path / "audit.sqlite3"}',connect_args={'check_same_thread':False})
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng,autoflush=False,expire_on_commit=False)


def _camera(db, cid:int, name='OldName', host='192.168.0.10', ref=''):
    row=CameraDevice(id=cid,name=name,host=host,secret_ref=ref,username_hint='admin',secret_generation=0,
        enabled=True,mock_mode=True,created_at=datetime.now(timezone.utc))
    db.add(row)
    db.flush()
    return row


def test_retry_must_not_scrub_uncommitted_active_staging(tmp_path):
    """C11: admin retry must not delete staged blob owned by an in-flight request."""
    sm=_db(tmp_path);secrets=SecretsStore(tmp_path/'data')
    live=secrets.put_camera_secret(101,'admin','OldPassA123')
    with sm() as db:
        _camera(db,101,ref=live)
        db.commit()
    with sm() as db:
        staged=secrets.stage_camera_secret(101,'admin','NewPassA456')
        queue_promote(db,staged_ref=staged,live_ref=live,camera_id=101,secrets=secrets)
        try:
            assert secrets.has_secret(staged)
            recover_pending_outbox(secrets,sm)  # another request, before this transaction commits
            assert secrets.has_secret(staged), 'Concurrent retry deleted an active uncommitted staged credential'
        finally:
            db.rollback()
            abort_outbox_after_rollback(secrets,db)


def test_refresh_does_not_discard_preexisting_camera_metadata_edits(tmp_path):
    """C12: PATCH name/host/model + REPLACE should retain camera metadata."""
    sm=_db(tmp_path);secrets=SecretsStore(tmp_path/'data')
    live=secrets.put_camera_secret(102,'admin','OldPassB123')
    with sm() as db:
        _camera(db,102,ref=live)
        db.commit()
    with sm() as db:
        row=db.get(CameraDevice,102)
        row.name='NewName'
        row.host='192.168.0.222'
        row.model='NewModel'
        staged=secrets.stage_camera_secret(102,'admin','NewPassB456')
        queue_promote(db,staged_ref=staged,live_ref=live,camera_id=102,secrets=secrets)
        try:
            assert (row.name,row.host,row.model)==('NewName','192.168.0.222','NewModel'), 'db.refresh discarded dirty camera edits'
        finally:
            db.rollback()
            abort_outbox_after_rollback(secrets,db)


def test_postcommit_fs_failure_must_return_real_http_503(app_client):
    """C13: external API response must never be HTTP 200 for incomplete commit."""
    _client,app=app_client
    with TestClient(app,raise_server_exceptions=False) as client:
        auth=client.post('/api/v1/auth/login',json={'username':'admin','password':'TestAdminPass!234'})
        assert auth.status_code==200
        headers={'X-CSRF-Token':auth.json()['csrf_token']}
        created=client.post('/api/v1/cameras',headers=headers,json={
            'name':'HTTP test','host':'192.168.0.99','username':'admin','password':'OldPassC123',
            'credential_action':'replace','mock_mode':True})
        assert created.status_code==200
        cid=created.json()['id']
        with patch.object(app.state.container.secrets,'promote_staged_camera_secret',side_effect=OSError('synthetic_disk_full')):
            response=client.patch(f'/api/v1/cameras/{cid}',headers=headers,json={
                'credential_action':'replace','username':'admin','password':'NewPassC456'})
        assert response.status_code==503, f'Postcommit failure returned HTTP {response.status_code}, expected 503'
        assert response.json()['detail']['code']=='SECRET_FS_OUTBOX_INCOMPLETE'


def test_old_pending_delete_must_not_delete_recreated_camera_id(tmp_path):
    """C14: SQLite may reuse hard-deleted camera numeric ID; old intent must be fenced."""
    sm=_db(tmp_path);secrets=SecretsStore(tmp_path/'data')
    with sm() as db:
        row=CameraDevice(name='old',host='192.168.0.1',enabled=True,
            mock_mode=True,created_at=datetime.now(timezone.utc),secret_generation=0)
        db.add(row);db.flush();old_id=row.id
        old_ref=secrets.put_camera_secret(old_id,'admin','OldPassD123')
        row.secret_ref=old_ref
        db.commit()
    with sm() as db:
        db.delete(db.get(CameraDevice,old_id));db.flush()
        old_op=queue_delete(db,old_ref,camera_id=old_id)
        old_op_id=old_op.id
        db.commit()
        release_session_credential_locks(db)  # synthetic crash before postcommit apply
        db.info.clear()
    with sm() as db:
        row=CameraDevice(name='new',host='192.168.0.2',enabled=True,mock_mode=True,
            created_at=datetime.now(timezone.utc),secret_generation=0)
        db.add(row);db.flush();new_id=row.id
        assert new_id==old_id, 'Fixture requires SQLite reused numeric primary key'
        live=secrets.live_camera_ref(new_id)
        staged=secrets.stage_camera_secret(new_id,'admin','NewPassD456')
        queue_promote(db,staged_ref=staged,live_ref=live,camera_id=new_id,secrets=secrets)
        row.secret_ref=live
        db.commit()
        assert apply_outbox_after_commit(secrets,db)==[]
    assert secrets.has_secret(live)
    process_outbox_row(secrets,sm,old_op_id)
    assert secrets.has_secret(live), 'Old DELETE erased new camera credential after numeric ID reuse'
