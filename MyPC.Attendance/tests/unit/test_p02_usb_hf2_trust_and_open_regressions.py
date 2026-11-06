"""P02-USB-HF2 independent regressions — expected RED on PR #25 / HF1.

Synthetic only. Assert production trust rules (no test-only bypass flags).
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from app.vision.camera.usb_device import (
    UsbDeviceInfo,
    dshow_open_target,
    enrich_for_capture,
    fingerprint_stable_id,
    resolve_device,
    set_usb_enumerator_for_tests,
)
from app.vision.camera.usb_uvc_gateway import LiveUsbUvcGateway, _default_open_capture


def test_enrich_for_capture_does_not_fabricate_mapping_verified():
    sid = fingerprint_stable_id("USB\\VID_0BDA&PID_58B0\\UGREEN-NOMAP")
    raw = UsbDeviceInfo(
        stable_id=sid,
        friendly_name="UGREEN Camera 4K",
        index_hint=None,
        ambiguous=False,
        mapping_verified=False,
    )
    out = enrich_for_capture(raw)
    assert out.mapping_verified is False, (
        "enrich_for_capture must not escalate mapping_verified from friendly name alone"
    )
    assert out.index_hint is None


def test_link_wmi_without_dshow_stays_unverified():
    from app.vision.camera.usb_device import DirectShowEnumerator

    enum = DirectShowEnumerator()
    sid = fingerprint_stable_id("USB\\VID_0BDA&PID_58B0\\UGREEN-EMPTY-DSHOW")
    wmi = [
        UsbDeviceInfo(
            stable_id=sid,
            friendly_name="UGREEN Camera 4K",
            ambiguous=False,
            mapping_verified=False,
        )
    ]
    linked = enum._link_wmi_to_dshow(wmi, [])
    assert linked
    assert linked[0].mapping_verified is False
    assert linked[0].index_hint is None


def test_duplicate_friendly_names_fail_closed_even_without_dshow():
    from app.vision.camera.usb_device import DirectShowEnumerator

    enum = DirectShowEnumerator()
    a = fingerprint_stable_id("USB\\VID_AAAA&PID_0001\\A")
    b = fingerprint_stable_id("USB\\VID_BBBB&PID_0002\\B")
    wmi = [
        UsbDeviceInfo(stable_id=a, friendly_name="UGREEN Camera 4K", ambiguous=False),
        UsbDeviceInfo(stable_id=b, friendly_name="UGREEN Camera 4K", ambiguous=False),
    ]
    linked = enum._link_wmi_to_dshow(wmi, [])
    assert all(d.ambiguous or not d.mapping_verified for d in linked)
    assert all(d.mapping_verified is False for d in linked)


def test_default_open_capture_rejects_ffmpeg_video_name_for_dshow():
    """OpenCV CAP_DSHOW is index-based — video=Name is FFmpeg syntax, not DSHOW."""
    with pytest.raises((TypeError, ValueError, RuntimeError, OSError)):
        cap = _default_open_capture("video=UGREEN Camera 4K", "dshow")
        # If a mock/opencv accepts the string without error, opening must not claim success
        # for trusted LIVE — require isOpened False or raise.
        if cap is not None and getattr(cap, "isOpened", lambda: False)():
            try:
                cap.release()
            except Exception:
                pass
            pytest.fail("CAP_DSHOW must not treat video=Name as a verified open target")


def test_reresolve_clears_stale_index_when_mapping_lost():
    sid = fingerprint_stable_id("USB\\VID_0BDA&PID_58B0\\UGREEN-STALE-IDX")

    class EnumLost:
        def list_devices(self):
            # Current enumeration: PnP still present, capture mapping gone
            return [
                UsbDeviceInfo(
                    stable_id=sid,
                    friendly_name="UGREEN Camera 4K",
                    index_hint=None,
                    ambiguous=False,
                    mapping_verified=False,
                    capture_mapping_verified=False,
                    pnp_id_found=True,
                )
            ]

    set_usb_enumerator_for_tests(EnumLost())
    try:
        gw = LiveUsbUvcGateway(
            camera_id="1",
            stable_id=sid,
            index=2,  # stale leftover from before unplug/reorder
            friendly_name="UGREEN Camera 4K",
            open_capture=lambda i, b: (_ for _ in ()).throw(RuntimeError("no open")),
            allow_msmf_fallback=False,
        )
        assert gw._index == 2
        with pytest.raises(ValueError):
            gw._reresolve_index()
        assert gw._index is None, "stale index must be cleared when mapping is lost"
        assert gw.get_latest_good_frame() is None
    finally:
        set_usb_enumerator_for_tests(None)


def test_resolve_trusted_live_requires_verified_index_not_name_only():
    sid = fingerprint_stable_id("USB\\VID_0BDA&PID_58B0\\UGREEN-NAME-ONLY")

    class E:
        def list_devices(self):
            return [
                UsbDeviceInfo(
                    stable_id=sid,
                    friendly_name="UGREEN Camera 4K",
                    index_hint=None,
                    ambiguous=False,
                    mapping_verified=False,
                )
            ]

    set_usb_enumerator_for_tests(E())
    try:
        with pytest.raises(ValueError) as ei:
            resolve_device(stable_id=sid, for_trusted_live=True)
        assert str(ei.value) in {
            "USB_IDENTITY_MISMATCH",
            "USB_INDEX_UNKNOWN",
            "USB_CAPTURE_UNVERIFIED",
        }
    finally:
        set_usb_enumerator_for_tests(None)
