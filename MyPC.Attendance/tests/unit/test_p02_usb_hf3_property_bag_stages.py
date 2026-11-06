"""P02-USB-HF3 property-bag / COM stage regressions (synthetic; no physical camera)."""

from __future__ import annotations

from app.vision.camera import dshow_com_enum as dce
from app.vision.camera.dshow_com_enum import (
    BLOCKER_BIND_TO_STORAGE_FAILED,
    BLOCKER_DEVICE_PATH_MISSING,
    BLOCKER_NONE,
    DshowEnumResult,
    DshowVideoMoniker,
    redacted_enum_diagnostics,
    set_dshow_enum_hook_for_tests,
)
from app.vision.camera.usb_device import (
    DirectShowEnumerator,
    UsbDeviceInfo,
    _DshowNamed,
    fingerprint_stable_id,
)


def teardown_function(_=None):
    set_dshow_enum_hook_for_tests(None)


def test_synthetic_property_bag_success_populates_stage_counters():
    dpath = r"\\?\usb#vid_0bda&pid_58b0&mi_00#GOOD#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"

    def hook():
        return DshowEnumResult(
            monikers=[
                DshowVideoMoniker(
                    ordinal=0,
                    friendly_name="UGREEN Camera 4K",
                    device_path=dpath,
                    device_path_fingerprint=dce.fingerprint_device_path(dpath),
                    property_bag_bind_ok=True,
                    friendly_name_read_ok=True,
                    device_path_read_ok=True,
                    device_path_canonical_ok=True,
                )
            ],
            blocker_code=BLOCKER_NONE,
            dshow_enum_ok=True,
            property_bag_bind_ok_count=1,
            friendly_name_read_ok_count=1,
            device_path_read_ok_count=1,
            device_path_canonical_ok_count=1,
        )

    set_dshow_enum_hook_for_tests(hook)
    res = dce.enumerate_video_capture_monikers()
    assert res.dshow_enum_ok is True
    assert res.property_bag_bind_ok_count == 1
    assert res.device_path_canonical_ok_count == 1
    diag = redacted_enum_diagnostics()
    assert diag["PROPERTY_BAG_BIND_OK_COUNT"] == 1
    assert diag["FRIENDLY_NAME_READ_OK_COUNT"] == 1
    assert "DevicePath" not in str(diag).lower() or diag.get("DSHOW_VIDEO_DEVICE_PATH_COUNT") == 1


def test_all_monikers_missing_properties_sets_truthful_blocker():
    def hook():
        rows = [
            DshowVideoMoniker(
                ordinal=i,
                friendly_name="",
                device_path="",
                device_path_fingerprint="",
                property_bag_bind_ok=False,
                first_blocker_code=BLOCKER_BIND_TO_STORAGE_FAILED,
                exception_class="COMError",
            )
            for i in range(3)
        ]
        return DshowEnumResult(
            monikers=rows,
            blocker_code=BLOCKER_BIND_TO_STORAGE_FAILED,
            dshow_enum_ok=True,
            property_bag_bind_ok_count=0,
            friendly_name_read_ok_count=0,
            device_path_read_ok_count=0,
            device_path_canonical_ok_count=0,
            first_blocker_code=BLOCKER_BIND_TO_STORAGE_FAILED,
            first_exception_class="COMError",
            com_release_warning_count=0,
        )

    set_dshow_enum_hook_for_tests(hook)
    res = dce.enumerate_video_capture_monikers()
    assert res.dshow_enum_ok is True
    assert len(res.monikers) == 3
    assert res.property_bag_bind_ok_count == 0
    assert res.blocker_code == BLOCKER_BIND_TO_STORAGE_FAILED
    # Must NOT fabricate mapping from empty bags
    enum = DirectShowEnumerator()
    pnp = r"USB\VID_0BDA&PID_58B0&MI_00\OWNER"
    wmi = [
        UsbDeviceInfo(
            stable_id=fingerprint_stable_id(pnp),
            friendly_name="UGREEN Camera 4K",
            pnp_id_found=True,
            _pnp_raw=pnp,
        )
    ]
    dshow = [
        _DshowNamed(index=m.ordinal, friendly_name=m.friendly_name, device_path="", device_path_fingerprint="")
        for m in res.monikers
    ]
    linked = enum._link_wmi_to_dshow(wmi, dshow)
    assert linked[0].capture_mapping_verified is False


def test_bind_ok_but_device_path_missing_is_distinct_blocker():
    def hook():
        return DshowEnumResult(
            monikers=[
                DshowVideoMoniker(
                    ordinal=0,
                    friendly_name="UGREEN Camera 4K",
                    device_path="",
                    device_path_fingerprint="",
                    property_bag_bind_ok=True,
                    friendly_name_read_ok=True,
                    device_path_read_ok=False,
                    first_blocker_code=BLOCKER_DEVICE_PATH_MISSING,
                )
            ],
            blocker_code=BLOCKER_DEVICE_PATH_MISSING,
            dshow_enum_ok=True,
            property_bag_bind_ok_count=1,
            friendly_name_read_ok_count=1,
            device_path_read_ok_count=0,
            first_blocker_code=BLOCKER_DEVICE_PATH_MISSING,
        )

    set_dshow_enum_hook_for_tests(hook)
    res = dce.enumerate_video_capture_monikers()
    assert res.first_blocker_code == BLOCKER_DEVICE_PATH_MISSING
    assert res.friendly_name_read_ok_count == 1
    assert res.device_path_read_ok_count == 0


def test_redacted_diagnostics_never_include_raw_paths():
    dpath = r"\\?\usb#vid_0bda&pid_58b0&mi_00#SECRET#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"

    def hook():
        return DshowEnumResult(
            monikers=[
                DshowVideoMoniker(
                    ordinal=0,
                    friendly_name="Cam",
                    device_path=dpath,
                    device_path_fingerprint=dce.fingerprint_device_path(dpath),
                    property_bag_bind_ok=True,
                    friendly_name_read_ok=True,
                    device_path_read_ok=True,
                    device_path_canonical_ok=True,
                )
            ],
            dshow_enum_ok=True,
            property_bag_bind_ok_count=1,
            friendly_name_read_ok_count=1,
            device_path_read_ok_count=1,
            device_path_canonical_ok_count=1,
        )

    set_dshow_enum_hook_for_tests(hook)
    dce.enumerate_video_capture_monikers()
    blob = str(redacted_enum_diagnostics())
    assert "SECRET" not in blob
    assert "vid_0bda" not in blob.lower()
    assert "\\\\?\\" not in blob


def test_safe_release_does_not_manual_release_owned_pointer():
    """Regression: comtypes finalizer owns Release — manual call double-frees."""
    import gc

    calls: list[str] = []

    class ManagedPointer:
        def Release(self):
            calls.append("release")

        def __del__(self):
            self.Release()

    ptr = ManagedPointer()
    warnings: list[str] = []
    dce._safe_release(ptr, warnings)
    ptr = None
    gc.collect()
    assert calls == ["release"]
    assert warnings == []


def test_enumerate_finalizes_release_warnings_after_root_cleanup_source():
    """Source-order contract: warning count must not freeze before root drops."""
    import inspect

    text = inspect.getsource(dce._enumerate_on_com_thread)
    metric_pos = text.find("com_release_warning_count=len(release_warnings)")
    root_cleanup_pos = text.find("_safe_release(bind_ctx, release_warnings)")
    assert root_cleanup_pos >= 0
    assert metric_pos < 0 or metric_pos > root_cleanup_pos
    # Telemetry must still be assigned from release_warnings after cleanup.
    assert "com_release_warning_count" in text[root_cleanup_pos:]
    assert "len(release_warnings)" in text[root_cleanup_pos:]


def test_com_release_warning_counter_exported():
    def hook():
        return DshowEnumResult(
            monikers=[],
            blocker_code=BLOCKER_NONE,
            dshow_enum_ok=True,
            com_release_warning_count=3,
            stage_notes=["release_warn:COMError"],
        )

    set_dshow_enum_hook_for_tests(hook)
    dce.enumerate_video_capture_monikers()
    diag = redacted_enum_diagnostics()
    assert diag["COM_RELEASE_WARNING_COUNT"] == 3


def test_source_uses_dedicated_com_worker_not_pythoncom_couninit_on_caller():
    import ast

    text = open(dce.__file__, encoding="utf-8").read()
    assert "mypc-dshow-com" in text
    assert "CoInitializeEx" in text
    assert "CreateBindCtx" in text
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {"CoInitialize", "CoUninitialize"}:
            # Disallow pythoncom.CoInitialize / CoUninitialize attribute use in code
            if isinstance(node.value, ast.Name) and node.value.id == "pythoncom":
                raise AssertionError("pythoncom COM init/uninit must not be used in dshow_com_enum")
            if isinstance(node.value, ast.Attribute) and node.value.attr == "pythoncom":
                raise AssertionError("pythoncom COM init/uninit must not be used in dshow_com_enum")
