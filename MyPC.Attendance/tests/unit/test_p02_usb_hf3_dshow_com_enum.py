"""P02-USB-HF3 regressions — DirectShow native COM enum + DevicePath mapping.

Synthetic only. Physical USB gates remain BLOCKED without owner Windows evidence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.vision.camera import dshow_com_enum as dce
from app.vision.camera.dshow_com_enum import (
    BLOCKER_PROGID_DISPATCH_FORBIDDEN,
    DshowEnumResult,
    DshowVideoMoniker,
    capture_instances_match,
    fingerprint_device_path,
    normalize_capture_instance_key,
    set_dshow_enum_hook_for_tests,
)
from app.vision.camera.usb_device import (
    DirectShowEnumerator,
    UsbDeviceInfo,
    enrich_for_capture,
    fingerprint_stable_id,
    resolve_device,
    set_usb_enumerator_for_tests,
)
from app.vision.camera.usb_uvc_gateway import LiveUsbUvcGateway, _default_open_capture


def teardown_function(_=None):
    set_dshow_enum_hook_for_tests(None)
    set_usb_enumerator_for_tests(None)


def test_source_forbids_systemdeviceenum_progid_dispatch():
    root = Path(__file__).resolve().parents[2] / "backend" / "app" / "vision" / "camera"
    # Strip docstrings/comments then assert no live ProgID Dispatch call remains
    import ast

    for name in ("usb_device.py", "dshow_com_enum.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                fname = ""
                if isinstance(func, ast.Name):
                    fname = func.id
                elif isinstance(func, ast.Attribute):
                    fname = func.attr
                if fname == "Dispatch" and node.args:
                    arg0 = node.args[0]
                    if isinstance(arg0, ast.Constant) and "SystemDeviceEnum" in str(arg0.value):
                        pytest.fail(f"{name}: forbidden Dispatch(SystemDeviceEnum) call")
    text = (root / "dshow_com_enum.py").read_text(encoding="utf-8")
    assert "CLSID_SystemDeviceEnum" in text
    assert "ICreateDevEnum" in text
    assert "DevicePath" in text
    assert "CoCreateInstance" in text


def test_progid_dispatch_helper_raises_forbidden():
    with pytest.raises(RuntimeError) as ei:
        dce.assert_progid_dispatch_forbidden()
    assert BLOCKER_PROGID_DISPATCH_FORBIDDEN in str(ei.value)


def test_normalize_and_match_devicepath_to_pnp():
    pnp = r"USB\VID_0BDA&PID_58B0&MI_00\6&ABCDEF&0&0000"
    dpath = r"\\?\usb#vid_0bda&pid_58b0&mi_00#6&abcdef&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
    assert capture_instances_match(dpath, pnp)
    assert normalize_capture_instance_key(dpath)
    assert fingerprint_device_path(dpath)


def test_audio_pnp_names_excluded_from_video_candidates():
    from app.vision.camera.usb_device import _is_video_pnp_candidate

    assert _is_video_pnp_candidate("UGREEN Camera 4K", r"USB\VID_0BDA&PID_58B0\X", "Camera")
    assert not _is_video_pnp_candidate(
        "Microphone (UGREEN Camera 4K)", r"USB\VID_0BDA&PID_58B0\Y", "Media"
    )
    assert not _is_video_pnp_candidate(
        "UGREEN Camera 4K Audio", r"USB\VID_0BDA&PID_58B0\Z", "MEDIA"
    )


def test_unique_devicepath_mapping_verifies_and_sets_ephemeral_index():
    enum = DirectShowEnumerator()
    pnp = r"USB\VID_0BDA&PID_58B0&MI_00\UGREEN-UNIQUE"
    sid = fingerprint_stable_id(pnp)
    dpath = r"\\?\usb#vid_0bda&pid_58b0&mi_00#ugreen-unique#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
    wmi = [
        UsbDeviceInfo(
            stable_id=sid,
            friendly_name="UGREEN Camera 4K",
            pnp_id_found=True,
            _pnp_raw=pnp,
        )
    ]
    from app.vision.camera.usb_device import _DshowNamed

    dshow = [
        _DshowNamed(
            index=2,
            friendly_name="UGREEN Camera 4K",
            device_path=dpath,
            device_path_fingerprint=fingerprint_device_path(dpath),
        )
    ]
    linked = enum._link_wmi_to_dshow(wmi, dshow)
    assert linked[0].capture_mapping_verified is True
    assert linked[0].mapping_verified is True
    assert linked[0].index_hint == 2
    assert linked[0].device_path_fingerprint


def test_duplicate_friendly_name_without_unique_devicepath_fail_closed():
    enum = DirectShowEnumerator()
    a = fingerprint_stable_id(r"USB\VID_AAAA&PID_0001\A")
    b = fingerprint_stable_id(r"USB\VID_BBBB&PID_0002\B")
    wmi = [
        UsbDeviceInfo(stable_id=a, friendly_name="SameCam", pnp_id_found=True, _pnp_raw=r"USB\VID_AAAA&PID_0001\A"),
        UsbDeviceInfo(stable_id=b, friendly_name="SameCam", pnp_id_found=True, _pnp_raw=r"USB\VID_BBBB&PID_0002\B"),
    ]
    linked = enum._link_wmi_to_dshow(wmi, [])
    assert all(not d.mapping_verified for d in linked)
    assert all(d.ambiguous or not d.capture_mapping_verified for d in linked)


def test_missing_device_path_stays_unverified_even_with_name_match():
    enum = DirectShowEnumerator()
    pnp = r"USB\VID_0BDA&PID_58B0\NO-DPATH"
    sid = fingerprint_stable_id(pnp)
    wmi = [
        UsbDeviceInfo(
            stable_id=sid,
            friendly_name="UGREEN Camera 4K",
            pnp_id_found=True,
            _pnp_raw=pnp,
        )
    ]
    from app.vision.camera.usb_device import _DshowNamed

    dshow = [
        _DshowNamed(index=2, friendly_name="UGREEN Camera 4K", device_path="", device_path_fingerprint="")
    ]
    linked = enum._link_wmi_to_dshow(wmi, dshow)
    assert linked[0].mapping_verified is False
    assert linked[0].capture_mapping_verified is False
    assert linked[0].index_hint is None


def test_pnp_present_dshow_empty_unverified():
    enum = DirectShowEnumerator()
    sid = fingerprint_stable_id(r"USB\VID_0BDA&PID_58B0\EMPTY")
    wmi = [
        UsbDeviceInfo(
            stable_id=sid,
            friendly_name="UGREEN Camera 4K",
            pnp_id_found=True,
            _pnp_raw=r"USB\VID_0BDA&PID_58B0\EMPTY",
        )
    ]
    linked = enum._link_wmi_to_dshow(wmi, [])
    assert linked[0].capture_mapping_verified is False


def test_name_only_does_not_verify_without_devicepath_match():
    enum = DirectShowEnumerator()
    pnp = r"USB\VID_0BDA&PID_58B0\NAMEONLY"
    sid = fingerprint_stable_id(pnp)
    other = r"\\?\usb#vid_1111&pid_2222#other#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
    wmi = [
        UsbDeviceInfo(
            stable_id=sid,
            friendly_name="UGREEN Camera 4K",
            pnp_id_found=True,
            _pnp_raw=pnp,
        )
    ]
    from app.vision.camera.usb_device import _DshowNamed

    dshow = [
        _DshowNamed(
            index=2,
            friendly_name="UGREEN Camera 4K",
            device_path=other,
            device_path_fingerprint=fingerprint_device_path(other),
        )
    ]
    linked = enum._link_wmi_to_dshow(wmi, dshow)
    assert linked[0].capture_mapping_verified is False


def test_index_reorder_same_devicepath_identity_ok():
    pnp = r"USB\VID_0BDA&PID_58B0&MI_00\REORDER"
    sid = fingerprint_stable_id(pnp)
    dpath = r"\\?\usb#vid_0bda&pid_58b0&mi_00#reorder#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
    fp = fingerprint_device_path(dpath)

    class E:
        def __init__(self, idx: int):
            self.idx = idx

        def list_devices(self):
            return [
                UsbDeviceInfo(
                    stable_id=sid,
                    friendly_name="UGREEN Camera 4K",
                    index_hint=self.idx,
                    ambiguous=False,
                    mapping_verified=True,
                    capture_mapping_verified=True,
                    pnp_id_found=True,
                    device_path_fingerprint=fp,
                    _pnp_raw=pnp,
                )
            ]

    set_usb_enumerator_for_tests(E(2))
    d1 = resolve_device(stable_id=sid, for_trusted_live=True)
    assert d1.index_hint == 2
    set_usb_enumerator_for_tests(E(0))
    d2 = resolve_device(stable_id=sid, for_trusted_live=True)
    assert d2.index_hint == 0
    assert d2.device_path_fingerprint == fp


def test_reresolve_rejects_wrong_camera_after_reorder():
    sid = fingerprint_stable_id(r"USB\VID_0BDA&PID_58B0\ORIG")

    class Wrong:
        def list_devices(self):
            return [
                UsbDeviceInfo(
                    stable_id=fingerprint_stable_id(r"USB\VID_FFFF&PID_FFFF\OTHER"),
                    friendly_name="Other Cam",
                    index_hint=2,
                    mapping_verified=True,
                    capture_mapping_verified=True,
                    device_path_fingerprint="other-fp",
                )
            ]

    set_usb_enumerator_for_tests(Wrong())
    gw = LiveUsbUvcGateway(
        camera_id="1",
        stable_id=sid,
        index=2,
        friendly_name="UGREEN Camera 4K",
        open_capture=lambda i, b: (_ for _ in ()).throw(RuntimeError("no")),
    )
    with pytest.raises(ValueError):
        gw._reresolve_index()
    assert gw._index is None


def test_enrich_still_never_fabricates_trust():
    sid = fingerprint_stable_id(r"USB\VID_0BDA&PID_58B0\NOFAB")
    out = enrich_for_capture(
        UsbDeviceInfo(stable_id=sid, friendly_name="UGREEN Camera 4K", mapping_verified=False)
    )
    assert out.mapping_verified is False


def test_default_open_still_rejects_ffmpeg_video_name():
    with pytest.raises((TypeError, ValueError, RuntimeError, OSError)):
        cap = _default_open_capture("video=UGREEN Camera 4K", "dshow")
        if cap is not None and getattr(cap, "isOpened", lambda: False)():
            try:
                cap.release()
            except Exception:
                pass
            pytest.fail("CAP_DSHOW must reject video=Name")


def test_hook_enum_returns_video_only_monikers():
    def hook():
        return DshowEnumResult(
            monikers=[
                DshowVideoMoniker(
                    ordinal=0,
                    friendly_name="UGREEN Camera 4K",
                    device_path=r"\\?\usb#vid_0bda&pid_58b0#x#{guid}\global",
                    device_path_fingerprint=fingerprint_device_path(
                        r"\\?\usb#vid_0bda&pid_58b0#x#{guid}\global"
                    ),
                )
            ]
        )

    set_dshow_enum_hook_for_tests(hook)
    res = dce.enumerate_video_capture_monikers()
    assert res.monikers
    assert all(m.ordinal >= 0 for m in res.monikers)
    src = Path(dce.__file__).read_text(encoding="utf-8")
    assert "CLSID_VideoInputDeviceCategory" in src
    assert "CLSID_AudioInputDeviceCategory" in src  # defined for exclusion docs
    # Production enumerator must create video category, not audio
    assert "CreateClassEnumerator" in src
    assert src.index("CLSID_VideoInputDeviceCategory") < src.index(
        "enumerate_video_capture_monikers"
    ) or "GUID(CLSID_VideoInputDeviceCategory)" in src
