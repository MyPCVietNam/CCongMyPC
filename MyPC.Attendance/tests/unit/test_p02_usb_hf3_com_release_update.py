"""Independent negative regressions for PR #27 at ff6789e.

Run from MyPC.Attendance root after copying to tests/unit:
  PYTHONPATH=backend python -m pytest -q tests/unit/test_p02_usb_hf3_com_release_update.py

Expected on pre-fix PR #27: 3 FAIL. No Windows USB or biometrics required.
"""

import gc
import inspect
import re
from pathlib import Path

from app.vision.camera import dshow_com_enum as dce


def test_automatic_com_pointer_finalizer_must_not_double_release():
    """Emulate comtypes 1.4.17 pointer ownership: __del__ invokes Release().

    comtypes 1.4.17: _post_coinit/unknwn.py _compointer_base.__del__ calls Release.
    Manually invoking Release and then disposing a Python pointer can call it twice.
    """
    calls = []

    class ManagedPointer:
        def Release(self):
            calls.append("release")

        def __del__(self):
            self.Release()

    ptr = ManagedPointer()
    warnings = []
    dce._safe_release(ptr, warnings)
    ptr = None
    gc.collect()
    assert len(calls) == 1, (
        f"COM pointer released {len(calls)} times, expected exactly once. "
        "Do not manually Release an owned comtypes pointer and then allow its "
        "__del__ to Release again."
    )
    assert not warnings


def test_update_script_must_not_pass_absolute_paths_as_rename_newname():
    root = Path(__file__).resolve().parents[2]
    ps = (root / "scripts/windows/p02_usb_hf3_candidate_18878.ps1").read_text(
        encoding="utf-8-sig"
    )
    assert not re.search(r"Rename-Item\s+\$srcDir\s+\$backup\b", ps), (
        "Rename-Item -NewName cannot be an absolute backup path. "
        "Use Split-Path -Leaf for same-directory rename, or Move-Item plus "
        "explicit validated backup/rollback."
    )
    assert not re.search(r"Rename-Item\s+\$stageSrc\s+\$srcDir\b", ps), (
        "Rename-Item -NewName cannot be an absolute src path. "
        "Use Split-Path -Leaf for same-directory rename or Move-Item safely."
    )


def test_com_release_warning_telemetry_must_account_for_root_cleanup():
    text = inspect.getsource(dce._enumerate_on_com_thread)
    metric_pos = text.find("com_release_warning_count=len(release_warnings)")
    root_cleanup_pos = text.find("_safe_release(bind_ctx, release_warnings)")
    assert root_cleanup_pos >= 0, "No explicit root COM pointer cleanup found"
    assert metric_pos < 0 or metric_pos > root_cleanup_pos, (
        "Release warning count was frozen before root pointer releases and "
        "CoUninitialize; failures in final cleanup are not observable. "
        "Finalize cleanup before producing the result/telemetry."
    )
