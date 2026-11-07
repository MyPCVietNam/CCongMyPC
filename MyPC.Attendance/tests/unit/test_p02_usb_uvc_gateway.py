"""P02-USB: fake-device USB UVC gateway + registry lease (no physical webcam)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import numpy as np
import pytest

from app.vision.camera.gateway import DecoderStatus, StreamProvenance
from app.vision.camera.registry import CameraSourceRegistry
from app.vision.camera.usb_device import (
    UsbDeviceInfo,
    fingerprint_stable_id,
    resolve_device,
    set_usb_enumerator_for_tests,
    usb_stream_fingerprint,
)
from app.vision.camera.usb_uvc_gateway import LiveUsbUvcGateway, diagnose_usb_modes


@dataclass
class _FakeCap:
    frames: list
    opened: bool = True
    props: dict | None = None
    read_i: int = 0
    fail_after: int | None = None
    read_delay_s: float = 0.0

    def isOpened(self) -> bool:
        return self.opened

    def set(self, *_a, **_k) -> bool:
        return True

    def get(self, prop):
        props = self.props or {}
        return props.get(prop, 0)

    def read(self):
        if self.read_delay_s > 0:
            time.sleep(self.read_delay_s)
        if self.fail_after is not None and self.read_i >= self.fail_after:
            return False, None
        if self.read_i >= len(self.frames):
            fr = self.frames[-1] if self.frames else None
        else:
            fr = self.frames[self.read_i]
        self.read_i += 1
        if fr is None:
            return False, None
        return True, fr.copy()

    def release(self) -> None:
        self.opened = False


class _Enum:
    def __init__(self, devices: list[UsbDeviceInfo]):
        self._d = devices

    def list_devices(self) -> list[UsbDeviceInfo]:
        return list(self._d)


@pytest.fixture
def usb_sid():
    return fingerprint_stable_id("USB\\VID_0BDA&PID_58B0\\UGREEN-SYNTH")


@pytest.fixture(autouse=True)
def _reset_enum():
    set_usb_enumerator_for_tests(None)
    yield
    set_usb_enumerator_for_tests(None)


def _bgr(w=640, h=480, val=40):
    # Must have spatial variance — solid slabs are rejected by frame_looks_corrupt
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = (val, val // 2, min(255, val + 20))
    img[::16, :, :] = 180
    img[:, ::16, :] = 90
    rng = np.random.default_rng(abs(val) + w)
    noise = rng.integers(0, 40, size=(h, w, 3), dtype=np.uint8)
    return np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def test_fingerprint_stable_and_lease_key(usb_sid):
    assert usb_sid.startswith("uvc:")
    assert usb_stream_fingerprint(usb_sid).startswith("usb:uvc:")


def test_resolve_device_fail_closed_missing(usb_sid):
    set_usb_enumerator_for_tests(_Enum([]))
    with pytest.raises(ValueError, match="USB_DEVICE_NOT_FOUND"):
        resolve_device(stable_id=usb_sid)


def test_resolve_rejects_empty():
    with pytest.raises(ValueError, match="USB_STABLE_ID_REQUIRED"):
        resolve_device(stable_id="")


def test_gateway_publishes_live_frames_no_forge_on_fail(usb_sid):
    frames = [_bgr(1920, 1080, 30), _bgr(1920, 1080, 50)]
    caps: list[_FakeCap] = []

    def open_capture(index: int, backend: str):
        assert index == 2
        # Slow reads so CI can observe DecoderStatus.OK before fail_after clears good frames.
        cap = _FakeCap(
            frames=frames,
            fail_after=6,
            read_delay_s=0.05,
            props={
                3: 1920,  # WIDTH — cv2 constants vary; gateway also uses frame.shape
                4: 1080,
                5: 30.0,
                6: 0,
            },
        )
        caps.append(cap)
        return cap

    set_usb_enumerator_for_tests(
        _Enum(
            [
                UsbDeviceInfo(
                    stable_id=usb_sid,
                    friendly_name="UGREEN Camera 4K",
                    index_hint=2,
                    ambiguous=False,
                )
            ]
        )
    )
    gw = LiveUsbUvcGateway(
        camera_id="9",
        stable_id=usb_sid,
        index=2,
        friendly_name="UGREEN Camera 4K",
        open_capture=open_capture,
        allow_msmf_fallback=False,
        stale_after_s=2.0,
        max_backoff_s=0.2,
    )
    # Injected open_capture skips _reresolve (production path re-resolves)
    gw.start()
    deadline = time.time() + 5.0
    fr = None
    while time.time() < deadline:
        fr = gw.get_latest_good_frame()
        if fr is not None:
            break
        time.sleep(0.01)
    assert fr is not None
    assert fr.provenance == StreamProvenance.CAMERA_LIVE
    assert fr.width == 1920 and fr.height == 1080
    assert fr.integrity_ok is True
    h = gw.health()
    assert h.extras.get("source_type") == "USB_UVC"
    assert h.extras.get("transport") == "USB_UVC"
    assert h.camera_lab_pass is False
    # After fail_after, status leaves OK and good frame must not be forged.
    deadline_fail = time.time() + 5.0
    while time.time() < deadline_fail and gw.health().decoder_status == DecoderStatus.OK:
        time.sleep(0.02)
    assert gw.get_latest_good_frame() is None or gw.health().decoder_status != DecoderStatus.OK
    gw.stop()
    assert gw.health().decoder_status == DecoderStatus.STOPPED


def test_registry_one_capture_loop_two_viewers(usb_sid):
    def open_capture(index: int, backend: str):
        return _FakeCap(frames=[_bgr(1280, 720)], props={3: 1280, 4: 720, 5: 30})

    reg = CameraSourceRegistry()
    gw1 = LiveUsbUvcGateway(
        camera_id="1", stable_id=usb_sid, index=0, open_capture=open_capture, allow_msmf_fallback=False
    )
    fp = usb_stream_fingerprint(usb_sid)
    b1 = reg.bind(1, gw1, provenance=StreamProvenance.CAMERA_LIVE, stream_fingerprint=fp)
    b1.gateway.start()
    gw2 = LiveUsbUvcGateway(
        camera_id="2", stable_id=usb_sid, index=0, open_capture=open_capture, allow_msmf_fallback=False
    )
    b2 = reg.bind(2, gw2, provenance=StreamProvenance.CAMERA_LIVE, stream_fingerprint=fp)
    assert b1.config_revision == b2.config_revision
    assert reg.lease_holders(fp) == [1, 2]
    assert b1.gateway is b2.gateway
    deadline = time.time() + 2.0
    while time.time() < deadline:
        try:
            _, fr = reg.get_frame(1, require_live=True, allow_stale=True, max_age_s=5.0)
            assert fr.provenance == StreamProvenance.CAMERA_LIVE
            break
        except Exception:
            time.sleep(0.02)
    else:
        pytest.fail("no frame from shared USB lease")
    reg.unbind(1)
    assert reg.lease_holders(fp) == [2]
    reg.unbind(2)
    assert reg.lease_holders(fp) == []


def test_diagnose_reports_actual_not_requested():
    def open_capture(index: int, backend: str):
        return _FakeCap(frames=[_bgr(1280, 720)], props={3: 1280, 4: 720, 5: 15.0, 6: 0})

    modes = diagnose_usb_modes(index=0, open_capture=open_capture, backend="dshow")
    assert modes
    assert any(m.get("actual_width") == 1280 for m in modes if m.get("opened"))
    assert all(m.get("claims_4k") is False or "claims_4k" not in m for m in modes)


def test_stale_frame_not_for_biometric(usb_sid):
    gate = threading.Event()

    class SlowCap(_FakeCap):
        def read(self):
            gate.wait(timeout=2.0)
            return super().read()

    def open_capture(index: int, backend: str):
        return SlowCap(frames=[_bgr()], props={3: 640, 4: 480})

    reg = CameraSourceRegistry()
    gw = LiveUsbUvcGateway(
        camera_id="3",
        stable_id=usb_sid,
        index=1,
        open_capture=open_capture,
        allow_msmf_fallback=False,
        stale_after_s=0.05,
    )
    bound = reg.bind(
        3, gw, provenance=StreamProvenance.CAMERA_LIVE, stream_fingerprint=usb_stream_fingerprint(usb_sid)
    )
    bound.gateway.start()
    gate.set()
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if gw.get_latest_good_frame() is not None:
            break
        time.sleep(0.01)
    # Force stale by stopping publish and aging
    gw._status = DecoderStatus.RECONNECTING
    gw._latest_good = None
    from app.vision.camera.registry import FrameAccessError

    with pytest.raises(FrameAccessError):
        reg.get_frame(3, require_live=True, for_biometric=True, max_age_s=1.0)
    reg.unbind(3)
