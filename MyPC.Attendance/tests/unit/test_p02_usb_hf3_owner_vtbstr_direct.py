"""Independent synthetic reproducer for comtypes IPropertyBag VT_BSTR direct VARIANT usage.

Expected RED with PR27 coinit-corrected but property-read-unfixed ZIP
(sha256 027b8b6...); expected GREEN after proper fix.
Run from MyPC.Attendance repo root:
    PYTHONPATH=backend python -m pytest -q tests/unit/test_hf3_owner_vtbstr_direct.py
This test does not access Windows COM, USB devices, frames, credentials or HMAC.
"""
from __future__ import annotations

import ctypes
import sys
from types import ModuleType

import pytest
from app.vision.camera import dshow_com_enum as dce


class FakeVariant(ctypes.Structure):
    _fields_ = [("vt", ctypes.c_ushort)]
    def __init__(self):
        super().__init__()
        self._value = None
    @property
    def value(self):
        return self._value
    @value.setter
    def value(self, v):
        self._value = v


@pytest.fixture
def fake_comtypes(monkeypatch):
    package = ModuleType("comtypes")
    package.__path__ = []
    automation = ModuleType("comtypes.automation")
    automation.VARIANT = FakeVariant
    automation.VT_BSTR = 8
    monkeypatch.setitem(sys.modules, "comtypes", package)
    monkeypatch.setitem(sys.modules, "comtypes.automation", automation)


class DirectVariantBag:
    def __init__(self, properties):
        self.properties = properties
        self.ok = 0
    def Read(self, name, var, err):
        if not isinstance(var, FakeVariant) or var.vt != 8:
            raise ValueError("expected direct VT_BSTR VARIANT, not byref / VT_EMPTY")
        if name not in self.properties:
            raise FileNotFoundError("DevicePath absent for this non-target moniker")
        var.value = self.properties[name]
        self.ok += 1


def test_friendlyname_vtbstr_direct(fake_comtypes):
    bag = DirectVariantBag({"FriendlyName": "UGREEN Camera 4K"})
    assert dce._read_propbag_str(bag, "FriendlyName") == "UGREEN Camera 4K"
    assert bag.ok == 1


def test_devicepath_vtbstr_direct(fake_comtypes):
    path = r"\\?\usb#vid_0bda&pid_58b0&mi_00#instance#{guid}\global"
    bag = DirectVariantBag({"DevicePath": path})
    assert dce._read_propbag_str(bag, "DevicePath") == path
    assert bag.ok == 1


def test_missing_property_is_not_fabricated(fake_comtypes):
    bag = DirectVariantBag({"FriendlyName": "Other camera"})
    with pytest.raises((FileNotFoundError, ValueError, RuntimeError, OSError)):
        dce._read_propbag_str(bag, "DevicePath")


def test_read_propbag_source_uses_vt_bstr_direct_not_byref():
    """Production must not call Read(..., byref(var), ...) or TypeError fallback."""
    import inspect

    src = inspect.getsource(dce._read_propbag_str)
    assert "VT_BSTR" in src
    assert "var.vt" in src
    assert "prop_bag.Read(name, var, None)" in src
    assert "Read(name, byref(var)" not in src
    assert "except TypeError" not in src


def test_three_monikers_one_devicepath_maps_unique_pnp():
    """Owner shape: 3 bags bind; only 1 DevicePath; unique PnP↔path verified."""
    from app.vision.camera.usb_device import (
        DirectShowEnumerator,
        UsbDeviceInfo,
        _DshowNamed,
        fingerprint_stable_id,
    )

    target = r"\\?\usb#vid_0bda&pid_58b0&mi_00#OWNERINST#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
    pnp = r"USB\VID_0BDA&PID_58B0&MI_00\OWNERINST"

    def hook():
        rows = [
            dce.DshowVideoMoniker(
                ordinal=0,
                friendly_name="Other A",
                device_path="",
                device_path_fingerprint="",
                property_bag_bind_ok=True,
                friendly_name_read_ok=True,
                device_path_read_ok=False,
                first_blocker_code=dce.BLOCKER_DEVICE_PATH_MISSING,
                hresult=dce._HRESULT_FILE_NOT_FOUND,
            ),
            dce.DshowVideoMoniker(
                ordinal=1,
                friendly_name="Other B",
                device_path="",
                device_path_fingerprint="",
                property_bag_bind_ok=True,
                friendly_name_read_ok=True,
                device_path_read_ok=False,
                first_blocker_code=dce.BLOCKER_DEVICE_PATH_MISSING,
                hresult=dce._HRESULT_FILE_NOT_FOUND,
            ),
            dce.DshowVideoMoniker(
                ordinal=2,
                friendly_name="UGREEN Camera 4K",
                device_path=target,
                device_path_fingerprint=dce.fingerprint_device_path(target),
                property_bag_bind_ok=True,
                friendly_name_read_ok=True,
                device_path_read_ok=True,
                device_path_canonical_ok=True,
            ),
        ]
        return dce.DshowEnumResult(
            monikers=rows,
            blocker_code=dce.BLOCKER_NONE,
            dshow_enum_ok=True,
            property_bag_bind_ok_count=3,
            friendly_name_read_ok_count=3,
            device_path_read_ok_count=1,
            device_path_canonical_ok_count=1,
            com_release_warning_count=0,
        )

    dce.set_dshow_enum_hook_for_tests(hook)
    try:
        res = dce.enumerate_video_capture_monikers()
        assert res.property_bag_bind_ok_count == 3
        assert res.friendly_name_read_ok_count == 3
        assert res.device_path_read_ok_count == 1
        assert res.com_release_warning_count == 0

        enum = DirectShowEnumerator()
        wmi = [
            UsbDeviceInfo(
                stable_id=fingerprint_stable_id(pnp),
                friendly_name="UGREEN Camera 4K",
                pnp_id_found=True,
                _pnp_raw=pnp,
            )
        ]
        dshow = [
            _DshowNamed(
                index=m.ordinal,
                friendly_name=m.friendly_name,
                device_path=m.device_path,
                device_path_fingerprint=m.device_path_fingerprint,
            )
            for m in res.monikers
        ]
        linked = enum._link_wmi_to_dshow(wmi, dshow)
        verified = [x for x in linked if x.capture_mapping_verified]
        assert len(verified) == 1
        assert verified[0].index_hint == 2
        # Name alone / missing paths never verify
        assert sum(1 for x in linked if x.capture_mapping_verified) == 1
    finally:
        dce.set_dshow_enum_hook_for_tests(None)


def test_missing_devicepath_exc_classified_as_absent_not_abi():
    class Exc:
        def __init__(self, hr):
            self.hresult = hr

    assert dce._is_missing_prop_exc(FileNotFoundError("x")) is True
    assert dce._is_missing_prop_exc(Exc(dce._HRESULT_FILE_NOT_FOUND)) is True  # type: ignore[arg-type]
    assert dce._is_missing_prop_exc(Exc(dce._HRESULT_E_INVALIDARG)) is False  # type: ignore[arg-type]
    assert dce._is_missing_prop_exc(ValueError("byref")) is False
