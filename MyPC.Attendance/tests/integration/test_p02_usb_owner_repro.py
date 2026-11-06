"""Independent PR24 USB operator-path regressions. Synthetic fake devices only.

EXPECT RED on PR24: user-visible USB binding must work with correctly mapped
PnP identity; ambiguous index-only devices must have an explicit safe path;
nonmaterial same USB rebind should not rotate trust revision.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.vision.camera.usb_device import (
    UsbDeviceInfo, fingerprint_stable_id, set_usb_enumerator_for_tests,
)


def _login(client):
    login = client.post('/api/v1/auth/login', json={'username':'admin','password':'TestAdminPass!234'})
    assert login.status_code == 200, login.text
    return {'X-CSRF-Token': login.json()['csrf_token']}


class _FakeCapture:
    def __init__(self):
        self.opened=True
        self.frame=np.random.default_rng(10).integers(25,125,(480,640,3),dtype=np.uint8)
    def isOpened(self): return self.opened
    def set(self,*args): return True
    def get(self,prop): return {3:640,4:480,5:20,6:0}.get(prop,0)
    def read(self): return True, self.frame.copy()
    def release(self): self.opened=False


def _set_enum_and_camera(app_client, *, stable_id, index_hint, ambiguous, mapping_verified=None):
    client, application=app_client
    headers=_login(client)
    verified = bool(mapping_verified) if mapping_verified is not None else (
        (not ambiguous) and index_hint is not None
    )
    row=UsbDeviceInfo(
        stable_id=stable_id,
        friendly_name='UGREEN Camera 4K',
        index_hint=index_hint,
        ambiguous=ambiguous,
        mapping_verified=verified,
        capture_mapping_verified=verified,
        pnp_id_found=True,
        device_path_fingerprint=('fp-' + stable_id[-16:]) if verified else '',
    )
    class Enumerator:
        def list_devices(self): return [row]
    set_usb_enumerator_for_tests(Enumerator())
    application.state.container.usb_open_capture=lambda i,be: _FakeCapture()
    created=client.post('/api/v1/cameras',headers=headers,json={
        'name':'UGREEN synthetic','source_type':'USB_UVC','host':'','mock_mode':False,'credential_action':'keep'
    })
    assert created.status_code == 200, created.text
    return client, application, headers,created.json()['id']


def _cleanup(application):
    set_usb_enumerator_for_tests(None)
    application.state.container.usb_open_capture=None


def test_pnp_identity_without_dshow_index_must_fail_closed_for_trusted_live(app_client):
    """HF2: PnP without CAPTURE_MAPPING_VERIFIED must not bind trusted LIVE."""
    sid=fingerprint_stable_id('USB\\VID_0BDA&PID_58B0\\UGREEN-FAKE-1')
    client,app,head,cid=_set_enum_and_camera(app_client,stable_id=sid,index_hint=None,ambiguous=False)
    try:
        r=client.post('/api/v1/cameras/gateway/live/configure-usb',headers=head,json={'camera_id':cid,'stable_id':sid})
        assert r.status_code == 409, r.text
        code = r.json()['detail']['code']
        assert code in {'USB_CAPTURE_UNVERIFIED', 'USB_INDEX_UNKNOWN', 'USB_IDENTITY_MISMATCH'}
    finally: _cleanup(app)


def test_index_probe_stays_fail_closed_without_verified_device_identity(app_client):
    """Do not open an unverified index-only camera or grant HMAC trust (expected PASS)."""
    sid=fingerprint_stable_id('opencv-index:2')
    client,app,head,cid=_set_enum_and_camera(app_client,stable_id=sid,index_hint=2,ambiguous=True)
    try:
        r=client.post('/api/v1/cameras/gateway/live/configure-usb',headers=head,json={'camera_id':cid,'stable_id':sid})
        assert r.status_code == 409, r.text
        assert r.json()['detail']['code'] == 'USB_IDENTITY_UNSTABLE'
    finally: _cleanup(app)


def test_same_usb_rebind_preserves_configuration_revision_without_material_change(app_client):
    """Rebind should not invalidate signed trust if same stable identity/config: RED."""
    sid=fingerprint_stable_id('USB\\VID_0BDA&PID_58B0\\UGREEN-FAKE-2')
    client,app,head,cid=_set_enum_and_camera(app_client,stable_id=sid,index_hint=2,ambiguous=False)
    try:
        r1=client.post('/api/v1/cameras/gateway/live/configure-usb',headers=head,json={'camera_id':cid,'stable_id':sid})
        assert r1.status_code==200, r1.text
        with app.state.container.session_factory() as db:
            from app.models.entities import CameraDevice
            rev1=db.get(CameraDevice,cid).config_revision
        r2=client.post('/api/v1/cameras/gateway/live/configure-usb',headers=head,json={'camera_id':cid,'stable_id':sid})
        assert r2.status_code==200, r2.text
        with app.state.container.session_factory() as db:
            rev2=db.get(CameraDevice,cid).config_revision
        assert rev1==rev2, f'Nonmaterial same-USB rebind rotated revision: {rev1} -> {rev2}'
    finally: _cleanup(app)
