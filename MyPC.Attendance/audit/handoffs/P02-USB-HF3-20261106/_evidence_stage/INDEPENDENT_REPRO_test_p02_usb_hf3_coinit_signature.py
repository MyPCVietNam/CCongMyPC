"""PR27 HF3 regression: comtypes 1.4.17 CoInitializeEx accepts only one flags arg.

Run: PYTHONPATH=backend python -m pytest -q tests/unit/test_p02_usb_hf3_coinit_signature.py
On pre-fix commit 22513784 / e0ad4aac this test MUST be RED.
On corrected PR27 code this test MUST be GREEN.
No Windows device, COM adapter, or camera required.
"""
from __future__ import annotations

import sys
from types import ModuleType

from app.vision.camera import dshow_com_enum as dce


def test_comtypes_coinitializeex_uses_flags_only(monkeypatch):
    calls = []
    fake = ModuleType("comtypes")

    # Actual comtypes 1.4.17 wrapper signature: CoInitializeEx(flags=None).
    def coinit(flags=None):
        calls.append(("coinit", flags))

    def couninit():
        calls.append(("couninit",))

    def cocreate(*args, **kwargs):
        calls.append(("cocreate",))
        raise RuntimeError("intentional fake COM stop; no hardware opened")

    fake.CoInitializeEx = coinit
    fake.CoUninitialize = couninit
    fake.CoCreateInstance = cocreate
    fake.GUID = lambda s: s
    fake.CLSCTX_INPROC_SERVER = 1
    monkeypatch.setitem(sys.modules, "comtypes", fake)
    monkeypatch.setattr(dce, "_build_com_interfaces", lambda: (None, None, None, None, None))

    result = dce._enumerate_on_com_thread()

    # Wrong two-argument call never reaches CoCreateInstance and yields coinit:TypeError.
    assert ("coinit", 2) in calls, (calls, result.stage_notes)
    assert ("cocreate",) in calls, (calls, result.stage_notes)
    assert ("couninit",) in calls, (calls, result.stage_notes)
    assert not any(x == "coinit:TypeError" for x in result.stage_notes)


def test_coinit_failure_has_distinct_stage_code():
    """An initialization failure must not be mislabeled as CoCreateInstance failure."""
    import inspect
    code = inspect.getsource(dce._enumerate_on_com_thread)
    assert "BLOCKER_COINIT_FAILED" in code, (
        "Classify CoInitializeEx failures as DSHOW_COINIT_FAILED, "
        "not DSHOW_COCREATE_FAILED."
    )
