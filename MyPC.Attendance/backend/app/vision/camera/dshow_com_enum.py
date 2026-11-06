"""Native DirectShow *video* device enumeration via typed COM (not IDispatch ProgID).

Root causes addressed across HF3:
- ProgID ``Dispatch('SystemDeviceEnum')`` → CO_E_CLASSSTRING (fixed earlier).
- Property-bag stage: BindToStorage / IPropertyBag.Read must be ABI-correct and
  must not silently treat failures as empty success.
- COM lifetime: do **not** mix ``pythoncom.CoInitialize`` with comtypes objects or
  ``CoUninitialize`` while WMI/other apartments still hold live IUnknowns. DShow
  enumeration runs on a dedicated COM worker thread; only plain DTOs cross threads.

References (Microsoft Learn):
- Using the System Device Enumerator
- Selecting a Capture Device (DevicePath unique video-capture identifier)
- COM library initialization / balanced uninitialization
"""

from __future__ import annotations

import hashlib
import logging
import platform
import queue
import re
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Well-known DirectShow GUIDs (strmiids)
CLSID_SystemDeviceEnum = "{62BE5D10-60EB-11d0-BD3B-00A0C911CE86}"
CLSID_VideoInputDeviceCategory = "{860BB310-5D01-11d0-BD3B-00A0C911CE86}"
CLSID_AudioInputDeviceCategory = "{33D9A762-90C8-11d0-BD43-00A0C911CE86}"
IID_ICreateDevEnum = "{29840822-5B84-11D0-BD3B-00A0C911CE86}"
IID_IPropertyBag = "{55272A00-42CB-11CE-8135-00AA004BB851}"

# Blocker / stage codes (redacted — never include raw PnP / DevicePath)
BLOCKER_NOT_WINDOWS = "NOT_WINDOWS"
BLOCKER_COMTYPES_MISSING = "COMTYPES_MISSING"
BLOCKER_COCREATE_FAILED = "DSHOW_COCREATE_FAILED"
BLOCKER_CLASS_ENUM_EMPTY = "DSHOW_VIDEO_CATEGORY_EMPTY"
BLOCKER_CLASS_ENUM_FAILED = "DSHOW_CLASS_ENUM_FAILED"
BLOCKER_PROGID_DISPATCH_FORBIDDEN = "DSHOW_PROGID_DISPATCH_FORBIDDEN"
BLOCKER_BIND_TO_STORAGE_FAILED = "DSHOW_BIND_TO_STORAGE_FAILED"
BLOCKER_FRIENDLY_NAME_READ_FAILED = "DSHOW_FRIENDLY_NAME_READ_FAILED"
BLOCKER_DEVICE_PATH_READ_FAILED = "DSHOW_DEVICE_PATH_READ_FAILED"
BLOCKER_DEVICE_PATH_MISSING = "DSHOW_DEVICE_PATH_MISSING_FROM_DRIVER"
BLOCKER_DEVICE_PATH_CANONICAL_FAILED = "DSHOW_DEVICE_PATH_CANONICAL_FAILED"
BLOCKER_NONE = ""

_COINIT_APARTMENTTHREADED = 0x2
_RPC_E_CHANGED_MODE = -2147417850  # 0x80010106


@dataclass(frozen=True)
class DshowVideoMoniker:
    """One CLSID_VideoInputDeviceCategory moniker (video only)."""

    ordinal: int
    friendly_name: str
    device_path: str  # raw — never log / never put in public API
    device_path_fingerprint: str  # sha256 hex of canonical identity; empty if missing
    # Per-moniker stage flags (safe / redacted)
    property_bag_bind_ok: bool = False
    friendly_name_read_ok: bool = False
    device_path_read_ok: bool = False
    device_path_canonical_ok: bool = False
    first_blocker_code: str = BLOCKER_NONE
    exception_class: str = ""
    hresult: int | None = None

    @property
    def has_device_path(self) -> bool:
        return bool(self.device_path.strip())


@dataclass
class DshowEnumResult:
    monikers: list[DshowVideoMoniker]
    blocker_code: str = BLOCKER_NONE
    hresult: int | None = None
    detail_vi: str = ""
    # Aggregate stage telemetry (owner-safe)
    dshow_enum_ok: bool = False
    property_bag_bind_ok_count: int = 0
    friendly_name_read_ok_count: int = 0
    device_path_read_ok_count: int = 0
    device_path_canonical_ok_count: int = 0
    first_blocker_code: str = BLOCKER_NONE
    first_exception_class: str = ""
    com_release_warning_count: int = 0
    stage_notes: list[str] = field(default_factory=list)


_last_enum_result: DshowEnumResult | None = None
_test_enum_hook: Any | None = None


def set_dshow_enum_hook_for_tests(hook: Any | None) -> None:
    global _test_enum_hook
    _test_enum_hook = hook


def get_last_dshow_enum_result() -> DshowEnumResult | None:
    return _last_enum_result


def fingerprint_device_path(device_path: str) -> str:
    """Fingerprint the *canonical video-function identity*, not a loose path substring."""
    parsed = parse_usb_video_function_id(device_path)
    if parsed is None:
        return ""
    return hashlib.sha256(parsed.encode("utf-8")).hexdigest()


def normalize_capture_instance_key(raw: str) -> str:
    """Canonicalize DirectShow DevicePath or WMI PNPDeviceID (separators only)."""
    s = (raw or "").strip().lower()
    if not s:
        return ""
    s = s.replace("/", "\\")
    if s.startswith("\\\\?\\"):
        s = s[4:]
    s = s.replace("#", "\\")
    brace = s.find("{")
    if brace >= 0:
        s = s[:brace].rstrip("\\")
    if s.endswith("\\global"):
        s = s[: -len("\\global")]
    s = re.sub(r"\\+", r"\\", s).strip("\\")
    return s


_USB_VIDEO_FN_RE = re.compile(
    r"^(?:usb\\)?vid_([0-9a-f]{4})&pid_([0-9a-f]{4})&mi_([0-9a-f]{2})\\(.+)$",
    re.IGNORECASE,
)


def parse_usb_video_function_id(raw: str) -> str | None:
    """Return canonical ``vid|pid|mi|instance`` for one USB video *function*."""
    key = normalize_capture_instance_key(raw)
    if not key:
        return None
    m = _USB_VIDEO_FN_RE.match(key)
    if not m:
        return None
    vid, pid, mi, inst = (
        m.group(1).lower(),
        m.group(2).lower(),
        m.group(3).lower(),
        m.group(4).lower(),
    )
    if not vid or not pid or not mi or not inst:
        return None
    if "\\" in inst or "/" in inst or ".." in inst:
        return None
    return f"vid={vid}|pid={pid}|mi={mi}|inst={inst}"


def capture_instances_match(a: str, b: str) -> bool:
    """True only when both sides parse to the *same* USB video function identity.

    Requires exact equality of VID, PID, MI, and the complete instance token.
    No substring / prefix containment; no MI-blind VID/PID matching.
    """
    pa = parse_usb_video_function_id(a)
    pb = parse_usb_video_function_id(b)
    if pa is None or pb is None:
        return False
    return pa == pb


def _exc_meta(exc: BaseException) -> tuple[str, int | None]:
    cls = type(exc).__name__
    hr = getattr(exc, "hresult", None)
    if hr is None and getattr(exc, "args", None):
        try:
            hr = int(exc.args[0])
        except Exception:
            hr = None
    try:
        hr_i = int(hr) if hr is not None else None
    except Exception:
        hr_i = None
    return cls, hr_i


def _safe_release(obj: Any, warnings: list[str]) -> None:
    """Release a COM pointer explicitly; record sanitized warning on failure."""
    if obj is None:
        return
    try:
        # comtypes pointers expose Release(); calling it avoids delayed GC after CoUninit
        release = getattr(obj, "Release", None)
        if callable(release):
            release()
    except Exception as exc:  # noqa: BLE001
        warnings.append(type(exc).__name__)
    try:
        # Drop Python ref so GC won't double-Release after apartment teardown
        del obj
    except Exception:
        pass


def _build_com_interfaces() -> tuple[Any, Any, Any, Any, Any]:
    """Define minimal typed DirectShow / OLE interfaces (ICreateDevEnum path)."""
    from ctypes import POINTER, c_int, c_ulong

    from comtypes import COMMETHOD, GUID, HRESULT, IUnknown
    from comtypes.persist import IPersist, IPropertyBag

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

    # IMoniker vtable after IPersistStream: BindToObject, BindToStorage first.
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

    return ICreateDevEnum, IEnumMoniker, IMoniker, IBindCtx, IPropertyBag


def _create_bind_ctx(IBindCtx: Any, warnings: list[str]) -> Any:
    """ole32 CreateBindCtx(0) — preferred non-NULL bind context for moniker BindToStorage."""
    from ctypes import POINTER, byref, c_ulong, windll

    from comtypes import GUID  # noqa: F401 — ensure comtypes loaded

    ole32 = windll.ole32
    # HRESULT CreateBindCtx(DWORD reserved, IBindCtx **ppbc)
    ppbc = POINTER(IBindCtx)()
    hr = ole32.CreateBindCtx(c_ulong(0), byref(ppbc))
    if hr != 0 or not ppbc:
        warnings.append(f"CreateBindCtx_hr={hr}")
        return None
    return ppbc


def _read_propbag_str(prop_bag: Any, name: str) -> str:
    """IPropertyBag::Read — check HRESULT semantics via raised COMError; clear VARIANT."""
    from ctypes import byref

    from comtypes.automation import VARIANT

    var = VARIANT()
    try:
        # comtypes IPropertyBag.Read(pszPropName, pVar, pErrorLog)
        # Pass VARIANT by reference for POINTER(VARIANT) in/out correctness.
        try:
            prop_bag.Read(name, byref(var), None)  # type: ignore[call-arg]
        except TypeError:
            prop_bag.Read(name, var, None)  # type: ignore[call-arg]
        val = var.value
        if val is None:
            return ""
        return str(val).strip()
    finally:
        try:
            var.value = None  # encourage VariantClear via comtypes
        except Exception:
            pass


def _enumerate_on_com_thread() -> DshowEnumResult:
    """Run entirely on the worker thread that owns the COM apartment."""
    from comtypes import GUID, CoCreateInstance, CoInitializeEx, CoUninitialize
    from comtypes import CLSCTX_INPROC_SERVER

    release_warnings: list[str] = []
    stage_notes: list[str] = []
    need_uninit = False
    try:
        CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
        need_uninit = True
    except Exception as exc:  # noqa: BLE001
        cls, hr = _exc_meta(exc)
        # RPC_E_CHANGED_MODE: apartment already initialized differently on this thread
        # (should not happen on a fresh worker). Fail closed rather than fight it.
        return DshowEnumResult(
            monikers=[],
            blocker_code=BLOCKER_COCREATE_FAILED,
            hresult=hr,
            detail_vi=f"CoInitializeEx thất bại ({cls}).",
            first_blocker_code=BLOCKER_COCREATE_FAILED,
            first_exception_class=cls,
            stage_notes=[f"coinit:{cls}"],
        )

    ICreateDevEnum, _IEnumMoniker, IMoniker, IBindCtx, IPropertyBag = _build_com_interfaces()
    devenum = None
    enum_mon = None
    bind_ctx = None
    out: list[DshowVideoMoniker] = []
    first_blocker = BLOCKER_NONE
    first_exc = ""
    first_hr: int | None = None

    try:
        try:
            devenum = CoCreateInstance(
                GUID(CLSID_SystemDeviceEnum),
                interface=ICreateDevEnum,
                clsctx=CLSCTX_INPROC_SERVER,
            )
        except Exception as exc:  # noqa: BLE001
            cls, hr = _exc_meta(exc)
            return DshowEnumResult(
                monikers=[],
                blocker_code=BLOCKER_COCREATE_FAILED,
                hresult=hr,
                detail_vi=(
                    "CoCreateInstance(CLSID_SystemDeviceEnum, ICreateDevEnum) thất bại — "
                    "không dùng Dispatch ProgID."
                ),
                first_blocker_code=BLOCKER_COCREATE_FAILED,
                first_exception_class=cls,
                stage_notes=[f"cocreate:{cls}"],
            )

        try:
            enum_mon = devenum.CreateClassEnumerator(
                GUID(CLSID_VideoInputDeviceCategory), 0
            )
        except Exception as exc:  # noqa: BLE001
            cls, hr = _exc_meta(exc)
            return DshowEnumResult(
                monikers=[],
                blocker_code=BLOCKER_CLASS_ENUM_FAILED,
                hresult=hr,
                detail_vi="CreateClassEnumerator(VideoInputDeviceCategory) thất bại.",
                first_blocker_code=BLOCKER_CLASS_ENUM_FAILED,
                first_exception_class=cls,
                stage_notes=[f"class_enum:{cls}"],
            )

        if enum_mon is None:
            return DshowEnumResult(
                monikers=[],
                blocker_code=BLOCKER_CLASS_ENUM_EMPTY,
                detail_vi="VideoInputDeviceCategory trống (S_FALSE).",
                first_blocker_code=BLOCKER_CLASS_ENUM_EMPTY,
                stage_notes=["class_enum:empty"],
            )

        stage_notes.append("DSHOW_ENUM_OK")
        bind_ctx = _create_bind_ctx(IBindCtx, release_warnings)
        iid_prop = GUID(IID_IPropertyBag)

        idx = 0
        while idx <= 64:
            moniker = None
            storage = None
            prop = None
            try:
                try:
                    moniker, fetched = enum_mon.Next(1)
                except ValueError:
                    break
                except Exception as exc:  # noqa: BLE001
                    cls, hr = _exc_meta(exc)
                    if not first_blocker:
                        first_blocker = BLOCKER_CLASS_ENUM_FAILED
                        first_exc = cls
                        first_hr = hr
                    stage_notes.append(f"next_fail:{cls}")
                    break
                if not fetched or moniker is None:
                    break

                friendly = ""
                device_path = ""
                bag_ok = False
                name_ok = False
                path_ok = False
                canon_ok = False
                mon_blocker = BLOCKER_NONE
                mon_exc = ""
                mon_hr: int | None = None

                try:
                    # IMoniker::BindToStorage(pbc, NULL, IID_IPropertyBag, ...)
                    storage = moniker.BindToStorage(bind_ctx, None, iid_prop)
                    if storage is None:
                        raise RuntimeError("BindToStorage_returned_null")
                    prop = storage.QueryInterface(IPropertyBag)
                    bag_ok = True
                except Exception as exc:  # noqa: BLE001
                    mon_exc, mon_hr = _exc_meta(exc)
                    mon_blocker = BLOCKER_BIND_TO_STORAGE_FAILED
                    if not first_blocker:
                        first_blocker = mon_blocker
                        first_exc = mon_exc
                        first_hr = mon_hr
                    logger.info(
                        "dshow_bind_to_storage_failed ordinal=%s err=%s hr=%s",
                        idx,
                        mon_exc,
                        mon_hr,
                    )

                if bag_ok and prop is not None:
                    try:
                        friendly = _read_propbag_str(prop, "FriendlyName")[:128]
                        name_ok = bool(friendly)
                        if not name_ok:
                            mon_blocker = mon_blocker or BLOCKER_FRIENDLY_NAME_READ_FAILED
                    except Exception as exc:  # noqa: BLE001
                        mon_exc, mon_hr = _exc_meta(exc)
                        mon_blocker = BLOCKER_FRIENDLY_NAME_READ_FAILED
                        if not first_blocker:
                            first_blocker = mon_blocker
                            first_exc = mon_exc
                            first_hr = mon_hr
                    try:
                        device_path = _read_propbag_str(prop, "DevicePath")
                        path_ok = bool(device_path.strip())
                        if not path_ok:
                            # Bind OK but driver truly omitted DevicePath
                            if mon_blocker in (BLOCKER_NONE, BLOCKER_FRIENDLY_NAME_READ_FAILED):
                                mon_blocker = BLOCKER_DEVICE_PATH_MISSING
                    except Exception as exc:  # noqa: BLE001
                        mon_exc, mon_hr = _exc_meta(exc)
                        mon_blocker = BLOCKER_DEVICE_PATH_READ_FAILED
                        if not first_blocker:
                            first_blocker = mon_blocker
                            first_exc = mon_exc
                            first_hr = mon_hr

                fp = ""
                if path_ok:
                    fp = fingerprint_device_path(device_path)
                    canon_ok = bool(fp)
                    if not canon_ok:
                        mon_blocker = BLOCKER_DEVICE_PATH_CANONICAL_FAILED
                        if not first_blocker:
                            first_blocker = mon_blocker

                out.append(
                    DshowVideoMoniker(
                        ordinal=idx,
                        friendly_name=friendly,  # empty if unread — do not invent success
                        device_path=device_path,
                        device_path_fingerprint=fp,
                        property_bag_bind_ok=bag_ok,
                        friendly_name_read_ok=name_ok,
                        device_path_read_ok=path_ok,
                        device_path_canonical_ok=canon_ok,
                        first_blocker_code=mon_blocker,
                        exception_class=mon_exc,
                        hresult=mon_hr,
                    )
                )
                idx += 1
            finally:
                # Reverse-order release: prop → storage → moniker (before next / CoUninit)
                _safe_release(prop, release_warnings)
                prop = None
                _safe_release(storage, release_warnings)
                storage = None
                _safe_release(moniker, release_warnings)
                moniker = None

        bag_n = sum(1 for m in out if m.property_bag_bind_ok)
        name_n = sum(1 for m in out if m.friendly_name_read_ok)
        path_n = sum(1 for m in out if m.device_path_read_ok)
        canon_n = sum(1 for m in out if m.device_path_canonical_ok)

        # Aggregate blocker: enum OK but zero property bags is NOT success
        agg_blocker = BLOCKER_NONE
        if not out:
            agg_blocker = BLOCKER_CLASS_ENUM_EMPTY
        elif bag_n == 0:
            agg_blocker = first_blocker or BLOCKER_BIND_TO_STORAGE_FAILED
        elif path_n == 0:
            agg_blocker = first_blocker or BLOCKER_DEVICE_PATH_MISSING
        elif canon_n == 0:
            agg_blocker = first_blocker or BLOCKER_DEVICE_PATH_CANONICAL_FAILED

        detail = (
            f"DSHOW_ENUM_OK monikers={len(out)} bag_ok={bag_n} "
            f"name_ok={name_n} path_ok={path_n} canon_ok={canon_n}."
        )
        return DshowEnumResult(
            monikers=out,
            blocker_code=agg_blocker,
            hresult=first_hr,
            detail_vi=detail,
            dshow_enum_ok=True,
            property_bag_bind_ok_count=bag_n,
            friendly_name_read_ok_count=name_n,
            device_path_read_ok_count=path_n,
            device_path_canonical_ok_count=canon_n,
            first_blocker_code=first_blocker or agg_blocker,
            first_exception_class=first_exc,
            com_release_warning_count=len(release_warnings),
            stage_notes=stage_notes + ([f"release_warn:{x}" for x in release_warnings[:5]]),
        )
    finally:
        _safe_release(bind_ctx, release_warnings)
        bind_ctx = None
        _safe_release(enum_mon, release_warnings)
        enum_mon = None
        _safe_release(devenum, release_warnings)
        devenum = None
        if need_uninit:
            try:
                CoUninitialize()
            except Exception as exc:  # noqa: BLE001
                release_warnings.append(type(exc).__name__)


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
            first_blocker_code=BLOCKER_NOT_WINDOWS,
        )
        _last_enum_result = result
        return result

    try:
        import comtypes  # noqa: F401
    except Exception:
        result = DshowEnumResult(
            monikers=[],
            blocker_code=BLOCKER_COMTYPES_MISSING,
            detail_vi="Thiếu comtypes — cài requirements-windows.txt (comtypes).",
            first_blocker_code=BLOCKER_COMTYPES_MISSING,
        )
        _last_enum_result = result
        return result

    # Dedicated STA worker — isolates from WMI/pythoncom apartment on caller thread.
    q: queue.Queue[DshowEnumResult] = queue.Queue(maxsize=1)

    def _worker() -> None:
        try:
            q.put(_enumerate_on_com_thread())
        except Exception as exc:  # noqa: BLE001
            cls, hr = _exc_meta(exc)
            q.put(
                DshowEnumResult(
                    monikers=[],
                    blocker_code=BLOCKER_COCREATE_FAILED,
                    hresult=hr,
                    detail_vi=f"COM worker thất bại ({cls}).",
                    first_blocker_code=BLOCKER_COCREATE_FAILED,
                    first_exception_class=cls,
                )
            )

    t = threading.Thread(target=_worker, name="mypc-dshow-com", daemon=True)
    t.start()
    t.join(timeout=60.0)
    if t.is_alive():
        result = DshowEnumResult(
            monikers=[],
            blocker_code=BLOCKER_COCREATE_FAILED,
            detail_vi="COM worker timeout — enumeration aborted.",
            first_blocker_code=BLOCKER_COCREATE_FAILED,
            first_exception_class="TimeoutError",
        )
    else:
        try:
            result = q.get_nowait()
        except queue.Empty:
            result = DshowEnumResult(
                monikers=[],
                blocker_code=BLOCKER_COCREATE_FAILED,
                detail_vi="COM worker returned no result.",
                first_blocker_code=BLOCKER_COCREATE_FAILED,
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
        "DSHOW_ENUM_OK": bool(res.dshow_enum_ok),
        "DSHOW_VIDEO_MONIKER_COUNT": len(res.monikers),
        "PROPERTY_BAG_BIND_OK_COUNT": int(res.property_bag_bind_ok_count),
        "FRIENDLY_NAME_READ_OK_COUNT": int(res.friendly_name_read_ok_count),
        "DEVICE_PATH_READ_OK_COUNT": int(res.device_path_read_ok_count),
        "DEVICE_PATH_CANONICAL_OK_COUNT": int(res.device_path_canonical_ok_count),
        "DSHOW_VIDEO_DEVICE_PATH_COUNT": with_path,
        "DSHOW_BLOCKER_CODE": res.blocker_code or BLOCKER_NONE,
        "DSHOW_FIRST_BLOCKER_CODE": res.first_blocker_code or BLOCKER_NONE,
        "DSHOW_FIRST_EXCEPTION_CLASS": res.first_exception_class or "",
        "DSHOW_HRESULT": res.hresult,
        "COM_RELEASE_WARNING_COUNT": int(res.com_release_warning_count),
        "detail_vi": res.detail_vi,
        "progid_dispatch_used": False,
        "stage_notes": list(res.stage_notes[:12]),
    }
