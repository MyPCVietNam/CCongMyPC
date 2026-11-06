"""Independent negative tests against P02-USB-HF3 (PR #27).

Place this file in the repo tests directory or execute from repo root with
PYTHONPATH=backend pytest -q <path-to-file>.
No camera needed; all paths are synthetic (not owner device identifiers).
Expected: the negative cases FAIL on PR #27 current HEAD; after a fix they PASS.
"""
from app.vision.camera.dshow_com_enum import (
    capture_instances_match,
    fingerprint_device_path,
)
from app.vision.camera.usb_device import (
    DirectShowEnumerator,
    UsbDeviceInfo,
    _DshowNamed,
    fingerprint_stable_id,
)

SUFFIX = r"#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"


def dshow_path(instance: str, mi: str = "00") -> str:
    return rf"\\?\usb#vid_0bda&pid_58b0&mi_{mi}#{instance}{SUFFIX}"


def pnp_path(instance: str, mi: str = "00") -> str:
    return rf"USB\VID_0BDA&PID_58B0&MI_{mi}\{instance}"


def test_positive_normalized_identity_still_matches():
    assert capture_instances_match(dshow_path("A&ONE"), pnp_path("A&ONE"))


def test_distinct_instance_prefix_must_not_match():
    # Two different camera functions on one system; accidental prefix overlap
    assert not capture_instances_match(dshow_path("A&ONE2"), pnp_path("A&ONE"))
    assert not capture_instances_match(dshow_path("A&ONE"), pnp_path("A&ONE2"))


def test_distinct_usb_interface_mi_must_not_match():
    # Distinct USB composite-interface functions cannot share trust solely
    # because vid/pid and last instance token happen to coincide.
    assert not capture_instances_match(dshow_path("A&ONE", mi="01"), pnp_path("A&ONE", mi="00"))


def test_linker_fails_closed_when_dshow_has_different_instance():
    pnp = pnp_path("A&ONE")
    dpath = dshow_path("A&ONE2")
    wmi = UsbDeviceInfo(
        stable_id=fingerprint_stable_id(pnp),
        friendly_name="UGREEN Camera 4K",
        pnp_id_found=True,
        _pnp_raw=pnp,
    )
    mon = _DshowNamed(
        index=2,
        friendly_name="Another Camera",
        device_path=dpath,
        device_path_fingerprint=fingerprint_device_path(dpath),
    )
    out = DirectShowEnumerator()._link_wmi_to_dshow([wmi], [mon])
    assert len(out) == 1
    assert not out[0].mapping_verified
    assert not out[0].capture_mapping_verified
    assert out[0].index_hint is None
