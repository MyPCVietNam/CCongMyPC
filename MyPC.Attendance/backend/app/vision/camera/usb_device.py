"""Windows USB UVC device enumeration and stable identity (no secrets / no frames).

Persist hashed ``stable_id`` only (PnP instance path / device interface). OpenCV
indexes are ephemeral hints. Fail closed when identity is ambiguous or when a
verified PnP device cannot be uniquely linked to a capture open target.
"""

from __future__ import annotations

import hashlib
import logging
import platform
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)

SOURCE_TYPE_USB_UVC = "USB_UVC"
SOURCE_TYPE_RTSP = "RTSP"


@dataclass(frozen=True)
class UsbDeviceInfo:
    """Display-safe USB webcam descriptor."""

    stable_id: str
    friendly_name: str
    index_hint: int | None = None
    backend: str = "dshow"
    vid: str = ""
    pid: str = ""
    instance_path_redacted: str = ""
    ambiguous: bool = False
    mapping_verified: bool = False
    open_target: str = ""  # DirectShow "video=Friendly Name" or empty
    note_vi: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("instance_path_redacted", None)
        # open_target is display-safe friendly name form; keep for operator UX
        d["stable_id_short"] = (self.stable_id[:12] + "…") if len(self.stable_id) > 12 else self.stable_id
        d["trusted_live_eligible"] = bool(
            (not self.ambiguous) and self.mapping_verified and (self.index_hint is not None or self.open_target)
        )
        return d


class UsbEnumerator(Protocol):
    def list_devices(self) -> list[UsbDeviceInfo]: ...


def fingerprint_stable_id(raw: str) -> str:
    raw_n = (raw or "").strip().lower()
    if not raw_n:
        raise ValueError("empty_usb_identity")
    digest = hashlib.sha256(raw_n.encode("utf-8")).hexdigest()
    return f"uvc:{digest}"


def usb_stream_fingerprint(stable_id: str) -> str:
    """Physical stream lease key — one capture loop per stable device."""
    sid = (stable_id or "").strip()
    if not sid.startswith("uvc:"):
        sid = fingerprint_stable_id(sid)
    return f"usb:{sid}"


_VID_PID_RE = re.compile(r"vid_([0-9a-f]{4}).*pid_([0-9a-f]{4})", re.I)


def _parse_vid_pid(path: str) -> tuple[str, str]:
    m = _VID_PID_RE.search(path or "")
    if not m:
        return "", ""
    return m.group(1).lower(), m.group(2).lower()


def _redact_instance(path: str) -> str:
    if not path:
        return ""
    vid, pid = _parse_vid_pid(path)
    if vid and pid:
        return f"USB\\VID_{vid.upper()}&PID_{pid.upper()}\\…"
    return "USB\\…"


def _norm_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


@dataclass(frozen=True)
class _DshowNamed:
    index: int
    friendly_name: str


CaptureLinker = Callable[[list[UsbDeviceInfo]], list[UsbDeviceInfo]]


_test_capture_linker: CaptureLinker | None = None


def set_usb_capture_linker_for_tests(linker: CaptureLinker | None) -> None:
    global _test_capture_linker
    _test_capture_linker = linker


def dshow_open_target(friendly_name: str) -> str:
    name = (friendly_name or "").strip()
    if not name:
        return ""
    return f"video={name}"


class DirectShowEnumerator:
    """Enumerate + link Windows PnP identity to DirectShow capture targets.

    Win10/11: prefer WMI ``PNPDeviceID`` (hashed) + DirectShow friendly-name/index
    correlation. Never treat VID/PID or friendly-name alone as unique when duplicates
    exist. OpenCV index-only probes are ``ambiguous=True`` and ineligible for trusted LIVE.
    """

    def list_devices(self) -> list[UsbDeviceInfo]:
        if platform.system().lower() != "windows":
            devices = self._opencv_index_probe(
                note_vi="Không phải Windows — chỉ probe chỉ số OpenCV (không ổn định)."
            )
            return self._apply_linker(devices)
        wmi = self._try_wmi_pn_p()
        dshow = self._enumerate_dshow_named()
        if wmi:
            linked = self._link_wmi_to_dshow(wmi, dshow)
            return self._apply_linker(linked)
        if dshow:
            # Named DShow without PnP — treat as unstable (name collision risk)
            out = [
                UsbDeviceInfo(
                    stable_id=fingerprint_stable_id(f"dshow-name:{_norm_name(d.friendly_name)}:{d.index}"),
                    friendly_name=d.friendly_name[:128],
                    index_hint=d.index,
                    backend="dshow",
                    ambiguous=True,
                    mapping_verified=False,
                    open_target=dshow_open_target(d.friendly_name),
                    note_vi=(
                        "Có tên DirectShow nhưng thiếu PnP hashed — không đủ cho CAMERA_LAB / HMAC."
                    ),
                )
                for d in dshow
            ]
            return self._apply_linker(out)
        return self._apply_linker(
            self._opencv_index_probe(
                note_vi="Không lấy được PnP ổn định — chỉ số OpenCV tạm thời; bắt buộc chọn lại sau cắm/rút."
            )
        )

    def _apply_linker(self, devices: list[UsbDeviceInfo]) -> list[UsbDeviceInfo]:
        if _test_capture_linker is not None:
            try:
                return list(_test_capture_linker(devices))
            except Exception as exc:  # noqa: BLE001
                logger.info("usb_test_linker_failed err=%s", type(exc).__name__)
        return devices

    def _try_wmi_pn_p(self) -> list[UsbDeviceInfo]:
        try:
            import wmi  # type: ignore

            c = wmi.WMI()
            out: list[UsbDeviceInfo] = []
            seen: set[str] = set()
            for cam in c.Win32_PnPEntity():
                name = str(getattr(cam, "Name", "") or "")
                pnp = str(getattr(cam, "PNPDeviceID", "") or "")
                if not name or not pnp:
                    continue
                low = name.lower()
                if "camera" not in low and "webcam" not in low and "imaging" not in low:
                    if "usb\\vid_" not in pnp.lower() or "video" not in low:
                        continue
                stable = fingerprint_stable_id(pnp)
                if stable in seen:
                    continue
                seen.add(stable)
                vid, pid = _parse_vid_pid(pnp)
                out.append(
                    UsbDeviceInfo(
                        stable_id=stable,
                        friendly_name=name.strip()[:128],
                        index_hint=None,
                        backend="dshow",
                        vid=vid,
                        pid=pid,
                        instance_path_redacted=_redact_instance(pnp),
                        ambiguous=False,
                        mapping_verified=False,
                        open_target=dshow_open_target(name),
                        note_vi="Định danh PnP ổn định (hashed) — đang chờ liên kết DirectShow.",
                    )
                )
            return out
        except Exception as exc:  # noqa: BLE001
            logger.info("usb_wmi_enum_unavailable err=%s", type(exc).__name__)
            return []

    def _enumerate_dshow_named(self) -> list[_DshowNamed]:
        """List DirectShow video inputs with index + friendly name when possible."""
        named = self._try_pywin32_dshow_names()
        if named:
            return named
        return self._try_opencv_index_with_placeholder_names()

    def _try_pywin32_dshow_names(self) -> list[_DshowNamed]:
        """Optional pywin32 DirectShow device enumeration (Win10/11).

        Uses CLSID_VideoInputDeviceCategory monikers. Device paths stay in-process;
        only friendly names + ordinal index leave this function.
        """
        try:
            import pythoncom  # type: ignore
            from win32com.client import Dispatch  # type: ignore

            pythoncom.CoInitialize()
            # System device enumerator
            devenum = Dispatch("SystemDeviceEnum")
            # Video input category
            cat = "{860BB310-5D01-11D0-BD3B-00A0C911CE86}"
            enum = devenum.CreateClassEnumerator(cat, 0)
            if enum is None:
                return []
            out: list[_DshowNamed] = []
            idx = 0
            while True:
                moniker = enum.Next()
                if not moniker:
                    break
                try:
                    bag = moniker.BindToStorage()
                    name = str(bag.Read("FriendlyName", 0) or "").strip()
                except Exception:
                    name = ""
                if name:
                    out.append(_DshowNamed(index=idx, friendly_name=name[:128]))
                idx += 1
                if idx > 32:
                    break
            return out
        except Exception as exc:  # noqa: BLE001
            logger.info("usb_dshow_moniker_unavailable err=%s", type(exc).__name__)
            return []

    def _try_opencv_index_with_placeholder_names(self) -> list[_DshowNamed]:
        try:
            import cv2  # type: ignore
        except Exception:
            return []
        out: list[_DshowNamed] = []
        for idx in range(0, 8):
            cap = None
            try:
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    continue
                out.append(_DshowNamed(index=idx, friendly_name=f"OpenCV index {idx}"))
            except Exception:
                continue
            finally:
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
        return out

    def _link_wmi_to_dshow(
        self, wmi_devs: list[UsbDeviceInfo], dshow: list[_DshowNamed]
    ) -> list[UsbDeviceInfo]:
        if not dshow:
            # Verified PnP identity exists but no capture index yet — keep open_target by name
            return [
                replace(
                    d,
                    mapping_verified=bool(d.friendly_name),
                    open_target=d.open_target or dshow_open_target(d.friendly_name),
                    note_vi=(
                        "PnP hashed OK; chưa lấy được chỉ số DirectShow — "
                        "sẽ mở bằng tên hiển thị (video=…) nếu tên duy nhất."
                        if d.friendly_name
                        else "PnP hashed nhưng thiếu tên — không mở được."
                    ),
                )
                for d in wmi_devs
            ]

        # Count name collisions among DShow devices
        name_counts: dict[str, int] = {}
        for d in dshow:
            k = _norm_name(d.friendly_name)
            name_counts[k] = name_counts.get(k, 0) + 1

        # Count WMI name collisions
        wmi_name_counts: dict[str, int] = {}
        for w in wmi_devs:
            k = _norm_name(w.friendly_name)
            wmi_name_counts[k] = wmi_name_counts.get(k, 0) + 1

        out: list[UsbDeviceInfo] = []
        for w in wmi_devs:
            key = _norm_name(w.friendly_name)
            matches = [d for d in dshow if _norm_name(d.friendly_name) == key]
            if wmi_name_counts.get(key, 0) > 1 or name_counts.get(key, 0) > 1 or len(matches) > 1:
                out.append(
                    replace(
                        w,
                        ambiguous=True,
                        mapping_verified=False,
                        index_hint=None,
                        note_vi=(
                            "Nhiều webcam cùng tên hiển thị — không thể gắn uniquely. "
                            "Rút bớt thiết bị hoặc dùng cổng USB khác / cập nhật driver."
                        ),
                    )
                )
                continue
            if len(matches) == 1:
                m = matches[0]
                out.append(
                    replace(
                        w,
                        index_hint=m.index,
                        mapping_verified=True,
                        ambiguous=False,
                        open_target=dshow_open_target(w.friendly_name),
                        note_vi="PnP hashed + DirectShow index đã liên kết duy nhất.",
                    )
                )
                continue
            # No DShow name match — still allow open by friendly name if WMI name unique
            if w.friendly_name and wmi_name_counts.get(key, 0) == 1:
                out.append(
                    replace(
                        w,
                        mapping_verified=True,
                        open_target=dshow_open_target(w.friendly_name),
                        note_vi=(
                            "PnP hashed duy nhất; mở capture bằng tên DirectShow (video=…). "
                            "Chỉ số OpenCV có thể đổi sau cắm/rút."
                        ),
                    )
                )
            else:
                out.append(
                    replace(
                        w,
                        mapping_verified=False,
                        note_vi="Không liên kết được PnP với DirectShow — fail-closed.",
                    )
                )
        return out

    def _opencv_index_probe(self, *, note_vi: str) -> list[UsbDeviceInfo]:
        try:
            import cv2  # type: ignore
        except Exception:
            return []
        out: list[UsbDeviceInfo] = []
        for idx in range(0, 8):
            cap = None
            try:
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    cap.release()
                    cap = cv2.VideoCapture(idx, cv2.CAP_MSMF)
                if not cap.isOpened():
                    continue
                raw = f"opencv-index:{idx}"
                out.append(
                    UsbDeviceInfo(
                        stable_id=fingerprint_stable_id(raw),
                        friendly_name=f"OpenCV camera index {idx} (tạm thời)",
                        index_hint=idx,
                        backend="dshow",
                        ambiguous=True,
                        mapping_verified=False,
                        open_target="",
                        note_vi=note_vi,
                    )
                )
            except Exception:
                continue
            finally:
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
        return out


_default_enumerator: UsbEnumerator | None = None


def get_usb_enumerator() -> UsbEnumerator:
    global _default_enumerator
    if _default_enumerator is None:
        _default_enumerator = DirectShowEnumerator()
    return _default_enumerator


def set_usb_enumerator_for_tests(enum: UsbEnumerator | None) -> None:
    global _default_enumerator
    _default_enumerator = enum


def enrich_for_capture(dev: UsbDeviceInfo) -> UsbDeviceInfo:
    """Ensure a verified device has a capture open target (index and/or video=name)."""
    if dev.ambiguous:
        return dev
    if dev.mapping_verified and (dev.index_hint is not None or dev.open_target):
        return dev
    if not dev.ambiguous and (dev.friendly_name or "").strip():
        # Verified (non-ambiguous) PnP entry: open by DirectShow friendly name
        return replace(
            dev,
            mapping_verified=True,
            open_target=dev.open_target or dshow_open_target(dev.friendly_name),
            note_vi=dev.note_vi
            or "PnP hashed không ambiguous — mở bằng tên DirectShow (không hard-code index).",
        )
    return dev


def resolve_device(
    *,
    stable_id: str,
    enumerator: UsbEnumerator | None = None,
    for_trusted_live: bool = True,
) -> UsbDeviceInfo:
    """Match persisted stable_id; fail closed if missing/ambiguous/unmapped for LIVE."""
    enum = enumerator or get_usb_enumerator()
    sid = (stable_id or "").strip()
    if not sid:
        raise ValueError("USB_STABLE_ID_REQUIRED")
    matches = [d for d in enum.list_devices() if d.stable_id == sid]
    if not matches:
        raise ValueError("USB_DEVICE_NOT_FOUND")
    if len(matches) > 1:
        raise ValueError("USB_DEVICE_AMBIGUOUS")
    dev = enrich_for_capture(matches[0])
    if for_trusted_live:
        if dev.ambiguous:
            raise ValueError("USB_IDENTITY_UNSTABLE")
        if not dev.mapping_verified:
            raise ValueError("USB_IDENTITY_MISMATCH")
        if dev.index_hint is None and not (dev.open_target or "").strip():
            raise ValueError("USB_INDEX_UNKNOWN")
    return dev


def capture_open_arg(dev: UsbDeviceInfo) -> int | str:
    """Argument for VideoCapture / injectable open_capture — never forge identity."""
    if dev.index_hint is not None:
        return int(dev.index_hint)
    target = (dev.open_target or "").strip() or dshow_open_target(dev.friendly_name)
    if not target:
        raise ValueError("USB_INDEX_UNKNOWN")
    return target


CaptureFactory = Callable[..., Any]
