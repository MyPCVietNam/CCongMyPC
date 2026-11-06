"""Native DirectShow *video* device enumeration via typed COM (not IDispatch ProgID).

Root cause (P02-USB-HF2 owner lab): ``win32com.client.Dispatch('SystemDeviceEnum')``
raises ``CO_E_CLASSSTRING`` (0x800401F3). ``CLSID_SystemDeviceEnum`` is a native COM
object created with ``CoCreateInstance(..., IID_ICreateDevEnum)`` — it is **not** an
Automation ProgID.

References (Microsoft Learn):
- Using the System Device Enumerator
- Selecting a Capture Device (DevicePath is the unique video-capture identifier)
"""

from __future__ import annotations

import hashlib
import logging
import platform
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Well-known DirectShow GUIDs (strmiids)
CLSID_SystemDeviceEnum = "{62BE5D10-60EB-11d0-BD3B-00A0C911CE86}"
CLSID_VideoInputDeviceCategory = "{860BB310-5D01-11d0-BD3B-00A0C911CE86}"
CLSID_AudioInputDeviceCategory = "{33D9A762-90C8-11d0-BD43-00A0C911CE86}"
IID_ICreateDevEnum = "{29840822-5B84-11D0-BD3B-00A0C911CE86}"
IID_IPropertyBag = "{55272A00-42CB-11CE-8135-00AA004BB851}"

# S_FALSE from CreateClassEnumerator / IEnumMoniker.Next
_S_FALSE = 0x00000001
_S_OK = 0x00000000

# Blocker codes (redacted diagnostics — never include raw PnP / DevicePath)
BLOCKER_NOT_WINDOWS = "NOT_WINDOWS"
BLOCKER_COMTYPES_MISSING = "COMTYPES_MISSING"
BLOCKER_COCREATE_FAILED = "DSHOW_COCREATE_FAILED"
BLOCKER_CLASS_ENUM_EMPTY = "DSHOW_VIDEO_CATEGORY_EMPTY"
BLOCKER_CLASS_ENUM_FAILED = "DSHOW_CLASS_ENUM_FAILED"
BLOCKER_PROGID_DISPATCH_FORBIDDEN = "DSHOW_PROGID_DISPATCH_FORBIDDEN"
BLOCKER_NONE = ""


@dataclass(frozen=True)
class DshowVideoMoniker:
    """One CLSID_VideoInputDeviceCategory moniker (video only)."""

    ordinal: int
    friendly_name: str
    device_path: str  # raw — never log / never put in public API
    device_path_fingerprint: str  # sha256 hex of normalized path; empty if missing

    @property
    def has_device_path(self) -> bool:
        return bool(self.device_path.strip())


@dataclass
class DshowEnumResult:
    monikers: list[DshowVideoMoniker]
    blocker_code: str = BLOCKER_NONE
    hresult: int | None = None
    detail_vi: str = ""


_last_enum_result: DshowEnumResult | None = None
# Test injection hook — production path never uses Dispatch ProgID.
_test_enum_hook: Any | None = None


def set_dshow_enum_hook_for_tests(hook: Any | None) -> None:
    global _test_enum_hook
    _test_enum_hook = hook


def get_last_dshow_enum_result() -> DshowEnumResult | None:
    return _last_enum_result


def fingerprint_device_path(device_path: str) -> str:
    key = normalize_capture_instance_key(device_path)
    if not key:
        return ""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def normalize_capture_instance_key(raw: str) -> str:
    """Normalize DirectShow DevicePath or WMI PNPDeviceID for identity compare.

    DevicePath example (shape only): ``\\\\?\\usb#vid_xxxx&pid_yyyy&mi_00#inst#{guid}\\global``
    PnP example: ``USB\\VID_XXXX&PID_YYYY&MI_00\\inst``
    """
    s = (raw or "").strip().lower()
    if not s:
        return ""
    s = s.replace("/", "\\")
    if s.startswith("\\\\?\\"):
        s = s[4:]
    s = s.replace("#", "\\")
    # Drop KS category GUID suffix and trailing \global
    brace = s.find("{")
    if brace >= 0:
        s = s[:brace].rstrip("\\")
    if s.endswith("\\global"):
        s = s[: -len("\\global")]
    s = re.sub(r"\\+", r"\\", s).strip("\\")
    return s


def capture_instances_match(a: str, b: str) -> bool:
    """True when DevicePath and PnPDeviceID refer to the same USB video function."""
    na = normalize_capture_instance_key(a)
    nb = normalize_capture_instance_key(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # Containment after normalizing separators (DevicePath often wraps PnP instance)
    if na in nb or nb in na:
        return True
    # Compare vid/pid + trailing instance token
    def parts(n: str) -> tuple[str, str, str]:
        m = re.search(r"vid_([0-9a-f]{4}).*?pid_([0-9a-f]{4})", n)
        vid = m.group(1) if m else ""
        pid = m.group(2) if m else ""
        # last path segment as instance id
        inst = n.split("\\")[-1] if "\\" in n else n
        return vid, pid, inst

    va, pa, ia = parts(na)
    vb, pb, ib = parts(nb)
    if va and pa and va == vb and pa == pb and ia and ia == ib:
        return True
    return False


def _build_com_interfaces() -> tuple[Any, Any, Any, Any]:
    """Define minimal typed DirectShow / OLE interfaces (ICreateDevEnum path only)."""
    from ctypes import POINTER, c_int, c_ulong

    from comtypes import COMMETHOD, GUID, HRESULT, IUnknown
    from comtypes.persist import IPersist, IPropertyBag  # noqa: F401 — IPropertyBag used

    class IPersistStream(IPersist):
        _iid_ = GUID("{00000109-0000-0000-C000-000000000046}")
        _idlflags_: list = []

    class ISequentialStream(IUnknown):
        _iid_ = GUID("{0C733A30-2A1C-11CE-ADE5-00AA0044773D}")
        _idlflags_: list = []

    class IStream(ISequentialStream):
        _iid_ = GUID("{0000000C-0000-0000-C000-000000000046}")
        _idlflags_: list = []

    from ctypes.wintypes import ULARGE_INTEGER

    IPersistStream._methods_ = [
        COMMETHOD([], HRESULT, "IsDirty"),
        COMMETHOD([], HRESULT, "Load", (["in"], POINTER(IStream), "pstm")),
        COMMETHOD(
            [],
            HRESULT,
            "Save",
            (["in"], POINTER(IStream), "pstm"),
            (["in"], c_int, "fClearDirty"),
        ),
        COMMETHOD([], HRESULT, "GetSizeMax", (["out"], POINTER(ULARGE_INTEGER), "pcbSize")),
    ]

    class IEnumMoniker(IUnknown):
        _iid_ = GUID("{00000102-0000-0000-C000-000000000046}")
        _idlflags_: list = []

    class IMoniker(IPersistStream):
        _iid_ = GUID("{0000000F-0000-0000-C000-000000000046}")
        _idlflags_: list = []

    class IBindCtx(IUnknown):
        _iid_ = GUID("{0000000E-0000-0000-C000-000000000046}")
        _idlflags_: list = []

    IEnumMoniker._methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "Next",
            (["in"], c_ulong, "celt"),
            (["out"], POINTER(POINTER(IMoniker)), "rgelt"),
            (["out"], POINTER(c_ulong), "pceltFetched"),
        ),
        COMMETHOD([], HRESULT, "Skip", (["in"], c_ulong, "celt")),
        COMMETHOD([], HRESULT, "Reset"),
        COMMETHOD([], HRESULT, "Clone", (["out"], POINTER(POINTER(IEnumMoniker)), "ppenum")),
    ]

    IMoniker._methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "BindToObject",
            (["in"], POINTER(IBindCtx), "pbc"),
            (["in"], POINTER(IMoniker), "pmkToLeft"),
            (["in"], POINTER(GUID), "riidResult"),
            (["out"], POINTER(POINTER(IUnknown)), "ppvResult"),
        ),
        COMMETHOD(
            [],
            HRESULT,
            "BindToStorage",
            (["in"], POINTER(IBindCtx), "pbc"),
            (["in"], POINTER(IMoniker), "pmkToLeft"),
            (["in"], POINTER(GUID), "riid"),
            (["out"], POINTER(POINTER(IUnknown)), "ppvObj"),
        ),
    ]

    class ICreateDevEnum(IUnknown):
        _iid_ = GUID(IID_ICreateDevEnum)
        _idlflags_: list = []

    ICreateDevEnum._methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "CreateClassEnumerator",
            (["in"], POINTER(GUID), "clsidDeviceClass"),
            (["out"], POINTER(POINTER(IEnumMoniker)), "ppEnumMoniker"),
            (["in"], c_int, "dwFlags"),
        )
    ]

    return ICreateDevEnum, IEnumMoniker, IMoniker, IPropertyBag


def _read_propbag_str(prop_bag: Any, name: str) -> str:
    from comtypes.automation import VARIANT

    var = VARIANT()
    # IPropertyBag.Read(pszPropName, pVar, pErrorLog)
    prop_bag.Read(name, var, None)  # type: ignore[call-arg]
    val = var.value
    if val is None:
        return ""
    return str(val).strip()


def enumerate_video_capture_monikers() -> DshowEnumResult:
    """Enumerate CLSID_VideoInputDeviceCategory only (never audio capture category)."""
    global _last_enum_result

    if _test_enum_hook is not None:
        result = _test_enum_hook()
        _last_enum_result = result
        return result

    if platform.system().lower() != "windows":
        result = DshowEnumResult(
            monikers=[],
            blocker_code=BLOCKER_NOT_WINDOWS,
            detail_vi="Không phải Windows — bỏ qua DirectShow COM enum.",
        )
        _last_enum_result = result
        return result

    try:
        from comtypes import GUID, CoCreateInstance  # type: ignore
        from comtypes import CLSCTX_INPROC_SERVER  # type: ignore
    except Exception:
        result = DshowEnumResult(
            monikers=[],
            blocker_code=BLOCKER_COMTYPES_MISSING,
            detail_vi="Thiếu comtypes — cài requirements-windows.txt (comtypes).",
        )
        _last_enum_result = result
        return result

    ICreateDevEnum, _IEnumMoniker, IMoniker, IPropertyBag = _build_com_interfaces()

    # Ensure we never accidentally go through ProgID Dispatch
    try:
        import pythoncom  # type: ignore

        pythoncom.CoInitialize()
    except Exception:
        pass

    try:
        devenum = CoCreateInstance(
            GUID(CLSID_SystemDeviceEnum),
            interface=ICreateDevEnum,
            clsctx=CLSCTX_INPROC_SERVER,
        )
    except Exception as exc:  # noqa: BLE001
        hr = getattr(exc, "hresult", None) or getattr(exc, "args", [None])[0]
        try:
            hr_i = int(hr) if hr is not None else None
        except Exception:
            hr_i = None
        logger.info(
            "dshow_cocreate_failed err=%s hr=%s",
            type(exc).__name__,
            hr_i,
        )
        result = DshowEnumResult(
            monikers=[],
            blocker_code=BLOCKER_COCREATE_FAILED,
            hresult=hr_i,
            detail_vi=(
                "CoCreateInstance(CLSID_SystemDeviceEnum, ICreateDevEnum) thất bại — "
                "không dùng Dispatch ProgID."
            ),
        )
        _last_enum_result = result
        return result

    out: list[DshowVideoMoniker] = []
    try:
        # CreateClassEnumerator returns S_FALSE when category empty (not an exception)
        enum_mon = devenum.CreateClassEnumerator(GUID(CLSID_VideoInputDeviceCategory), 0)
    except Exception as exc:  # noqa: BLE001
        logger.info("dshow_class_enum_failed err=%s", type(exc).__name__)
        result = DshowEnumResult(
            monikers=[],
            blocker_code=BLOCKER_CLASS_ENUM_FAILED,
            detail_vi="CreateClassEnumerator(VideoInputDeviceCategory) thất bại.",
        )
        _last_enum_result = result
        return result

    if enum_mon is None:
        result = DshowEnumResult(
            monikers=[],
            blocker_code=BLOCKER_CLASS_ENUM_EMPTY,
            detail_vi="VideoInputDeviceCategory trống (S_FALSE) — không giả thành công.",
        )
        _last_enum_result = result
        return result

    idx = 0
    try:
        while idx <= 64:
            try:
                moniker, fetched = enum_mon.Next(1)
            except ValueError:
                # comtypes may raise ValueError on S_FALSE end-of-enum
                break
            except Exception:
                break
            if not fetched:
                break
            if moniker is None:
                break
            friendly = ""
            device_path = ""
            try:
                # BindToStorage(..., IID_IPropertyBag)
                storage = moniker.BindToStorage(None, None, IPropertyBag._iid_)
                prop = storage.QueryInterface(IPropertyBag)
                try:
                    friendly = _read_propbag_str(prop, "FriendlyName")[:128]
                except Exception:
                    friendly = ""
                try:
                    device_path = _read_propbag_str(prop, "DevicePath")
                except Exception:
                    device_path = ""
            except Exception as exc:  # noqa: BLE001
                logger.info("dshow_moniker_props_failed ordinal=%s err=%s", idx, type(exc).__name__)
            fp = fingerprint_device_path(device_path) if device_path else ""
            out.append(
                DshowVideoMoniker(
                    ordinal=idx,
                    friendly_name=friendly or f"video_input_{idx}",
                    device_path=device_path,
                    device_path_fingerprint=fp,
                )
            )
            idx += 1
    finally:
        try:
            del enum_mon
        except Exception:
            pass
        try:
            del devenum
        except Exception:
            pass

    result = DshowEnumResult(
        monikers=out,
        blocker_code=BLOCKER_NONE if out else BLOCKER_CLASS_ENUM_EMPTY,
        detail_vi=(
            f"Đã liệt kê {len(out)} video moniker (VideoInputDeviceCategory)."
            if out
            else "Không có video capture moniker."
        ),
    )
    _last_enum_result = result
    return result


def assert_progid_dispatch_forbidden() -> None:
    """Guard: SystemDeviceEnum must never be opened via IDispatch ProgID."""
    raise RuntimeError(BLOCKER_PROGID_DISPATCH_FORBIDDEN)


def redacted_enum_diagnostics() -> dict[str, Any]:
    """Owner-safe counters — no raw PnP / DevicePath / frames."""
    res = _last_enum_result or DshowEnumResult(monikers=[])
    with_path = sum(1 for m in res.monikers if m.has_device_path)
    return {
        "DSHOW_VIDEO_MONIKER_COUNT": len(res.monikers),
        "DSHOW_VIDEO_DEVICE_PATH_COUNT": with_path,
        "DSHOW_BLOCKER_CODE": res.blocker_code or BLOCKER_NONE,
        "DSHOW_HRESULT": res.hresult,
        "detail_vi": res.detail_vi,
        "progid_dispatch_used": False,
    }
