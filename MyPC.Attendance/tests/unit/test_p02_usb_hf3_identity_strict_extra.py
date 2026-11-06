"""Extra HF3 identity-boundary cases beyond the independent 4-case repro."""

from __future__ import annotations

from app.vision.camera.dshow_com_enum import (
    capture_instances_match,
    fingerprint_device_path,
    parse_usb_video_function_id,
)
from app.vision.camera.usb_device import (
    DirectShowEnumerator,
    UsbDeviceInfo,
    _DshowNamed,
    _is_video_pnp_candidate,
    fingerprint_stable_id,
)

SUFFIX = r"#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"


def _dshow(instance: str, mi: str = "00", vid: str = "0bda", pid: str = "58b0") -> str:
    return rf"\\?\usb#vid_{vid}&pid_{pid}&mi_{mi}#{instance}{SUFFIX}"


def _pnp(instance: str, mi: str = "00", vid: str = "0BDA", pid: str = "58B0") -> str:
    return rf"USB\VID_{vid}&PID_{pid}&MI_{mi}\{instance}"


def test_usb_audio_path_not_video_candidate():
    assert not _is_video_pnp_candidate(
        "Microphone (UGREEN Camera 4K)", _pnp("AUD"), "Media"
    )


def test_same_vid_pid_separate_instances_do_not_match():
    assert not capture_instances_match(_dshow("INST-A"), _pnp("INST-B"))


def test_shared_prefix_instance_tokens_do_not_match():
    assert not capture_instances_match(_dshow("CAM"), _pnp("CAMERA"))
    assert not capture_instances_match(_dshow("CAMERA"), _pnp("CAM"))


def test_missing_device_path_never_verifies():
    enum = DirectShowEnumerator()
    pnp = _pnp("ONLY-PNP")
    wmi = [
        UsbDeviceInfo(
            stable_id=fingerprint_stable_id(pnp),
            friendly_name="UGREEN Camera 4K",
            pnp_id_found=True,
            _pnp_raw=pnp,
        )
    ]
    mon = _DshowNamed(index=2, friendly_name="UGREEN Camera 4K", device_path="", device_path_fingerprint="")
    out = enum._link_wmi_to_dshow(wmi, [mon])
    assert not out[0].mapping_verified
    assert out[0].index_hint is None


def test_duplicate_same_name_cameras_ambiguous():
    enum = DirectShowEnumerator()
    a = _pnp("A")
    b = _pnp("B")
    wmi = [
        UsbDeviceInfo(stable_id=fingerprint_stable_id(a), friendly_name="Same", pnp_id_found=True, _pnp_raw=a),
        UsbDeviceInfo(stable_id=fingerprint_stable_id(b), friendly_name="Same", pnp_id_found=True, _pnp_raw=b),
    ]
    dshow = [
        _DshowNamed(
            index=0,
            friendly_name="Same",
            device_path=_dshow("A"),
            device_path_fingerprint=fingerprint_device_path(_dshow("A")),
        ),
        _DshowNamed(
            index=1,
            friendly_name="Same",
            device_path=_dshow("B"),
            device_path_fingerprint=fingerprint_device_path(_dshow("B")),
        ),
    ]
    out = enum._link_wmi_to_dshow(wmi, dshow)
    assert all(d.ambiguous and not d.mapping_verified for d in out)


def test_one_moniker_claimed_by_two_pnp_fail_closed():
    """Synthetic collision: two WMI rows normalize to same DevicePath identity."""
    enum = DirectShowEnumerator()
    # Same instance identity expressed twice with different stable_id inputs that
    # still match the same moniker under strict equality — impossible with distinct
    # PnP strings; instead simulate two WMI with identical _pnp_raw.
    pnp = _pnp("SHARED")
    dpath = _dshow("SHARED")
    fp = fingerprint_device_path(dpath)
    wmi = [
        UsbDeviceInfo(stable_id=fingerprint_stable_id(pnp + "|a"), friendly_name="CamA", pnp_id_found=True, _pnp_raw=pnp),
        UsbDeviceInfo(stable_id=fingerprint_stable_id(pnp + "|b"), friendly_name="CamB", pnp_id_found=True, _pnp_raw=pnp),
    ]
    mon = [_DshowNamed(index=2, friendly_name="Cam", device_path=dpath, device_path_fingerprint=fp)]
    out = enum._link_wmi_to_dshow(wmi, mon)
    assert all(not d.mapping_verified for d in out)
    assert all(d.ambiguous or d.index_hint is None for d in out)


def test_parse_requires_mi():
    assert parse_usb_video_function_id(r"USB\VID_0BDA&PID_58B0\NOMI") is None
    assert parse_usb_video_function_id(_pnp("OK")) is not None


def test_positive_unique_link_sets_ephemeral_index_only():
    enum = DirectShowEnumerator()
    pnp = _pnp("UNIQUE-OK")
    dpath = _dshow("UNIQUE-OK")
    fp = fingerprint_device_path(dpath)
    wmi = [
        UsbDeviceInfo(
            stable_id=fingerprint_stable_id(pnp),
            friendly_name="UGREEN Camera 4K",
            pnp_id_found=True,
            _pnp_raw=pnp,
        )
    ]
    # Wrong camera sits at previous index 2; correct device remapped to 0 after replug
    dshow = [
        _DshowNamed(index=0, friendly_name="UGREEN Camera 4K", device_path=dpath, device_path_fingerprint=fp),
        _DshowNamed(
            index=2,
            friendly_name="Other Webcam",
            device_path=_dshow("OTHER", vid="1111", pid="2222"),
            device_path_fingerprint=fingerprint_device_path(_dshow("OTHER", vid="1111", pid="2222")),
        ),
    ]
    out = enum._link_wmi_to_dshow(wmi, dshow)
    assert out[0].capture_mapping_verified is True
    assert out[0].index_hint == 0  # not stale index 2
    assert out[0].device_path_fingerprint == fp
