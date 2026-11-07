"""Windows-owner physical DirectShow property-bag verification.

Skipped unless MYPC_OWNER_WINDOWS_USB=1. Never mocks a physical PASS in CI.
"""

from __future__ import annotations

import os
import platform

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("MYPC_OWNER_WINDOWS_USB", "").strip() != "1"
    or platform.system().lower() != "windows",
    reason="Owner Windows USB flag not set — physical gate remains BLOCKED in CI",
)


def test_owner_windows_property_bag_and_mapping_live():
    from app.vision.camera.dshow_com_enum import enumerate_video_capture_monikers
    from app.vision.camera.usb_device import DirectShowEnumerator

    res = enumerate_video_capture_monikers()
    assert res.dshow_enum_ok is True
    assert res.com_release_warning_count == 0
    assert res.property_bag_bind_ok_count >= 1, res.first_blocker_code
    assert res.friendly_name_read_ok_count >= 1, res.first_blocker_code
    assert res.device_path_read_ok_count >= 1, (
        f"blocker={res.first_blocker_code} exc={res.first_exception_class}"
    )
    assert res.device_path_canonical_ok_count >= 1

    devices = DirectShowEnumerator().list_devices()
    verified = [d for d in devices if d.capture_mapping_verified and d.device_path_fingerprint]
    assert verified, "CAPTURE_MAPPING_VERIFIED expected on owner Windows after property-bag fix"
    assert verified[0].index_hint is not None


def test_owner_windows_repeated_enumeration_no_com_leak_warnings():
    from app.vision.camera.dshow_com_enum import enumerate_video_capture_monikers

    warns = 0
    for _ in range(20):
        res = enumerate_video_capture_monikers()
        warns += int(res.com_release_warning_count)
        assert res.dshow_enum_ok is True
        assert res.first_blocker_code != "DSHOW_COINIT_FAILED", res.stage_notes
        assert "coinit:TypeError" not in list(res.stage_notes)
    assert warns == 0, f"COM release warnings across 20 cycles: {warns}"


def test_owner_windows_sta_worker_init_uninit_and_property_bag():
    """Real STA worker: CoInitializeEx(flags) must succeed; bag/path stages truthfully counted.

    Synthetic CI must never mark this PASS — gated by MYPC_OWNER_WINDOWS_USB=1.
    """
    from app.vision.camera.dshow_com_enum import (
        BLOCKER_COINIT_FAILED,
        enumerate_video_capture_monikers,
        redacted_enum_diagnostics,
    )

    res = enumerate_video_capture_monikers()
    diag = redacted_enum_diagnostics()
    assert res.first_blocker_code != BLOCKER_COINIT_FAILED, diag
    assert diag.get("DSHOW_FIRST_EXCEPTION_CLASS") != "TypeError" or res.dshow_enum_ok
    assert res.dshow_enum_ok is True, diag
    assert res.property_bag_bind_ok_count >= 1, diag
    assert res.device_path_read_ok_count >= 1, diag
    assert int(diag.get("COM_RELEASE_WARNING_COUNT", -1)) == 0
