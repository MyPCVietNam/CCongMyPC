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
