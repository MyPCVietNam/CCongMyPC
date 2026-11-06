"""Windows USB UVC device enumeration and stable identity (no secrets / no frames).

Persist hashed ``stable_id`` only (PnP instance path). OpenCV indexes are ephemeral.
``mapping_verified`` is True ONLY when a unique DirectShow index was correlated to
that PnP identity — never from friendly-name alone, VID/PID alone, or empty DShow lists.
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
    # Diagnostic stages (redacted) — never imply LIVE from PnP alone
    pnp_id_found: bool = False
    capture_mapping_verified: bool = False
    note_vi: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("instance_path_redacted", None)
        d["stable_id_short"] = (self.stable_id[:12] + "…") if len(self.stable_id) > 12 else self.stable_id
        d["trusted_live_eligible"] = bool(
            (not self.ambiguous)
            and self.mapping_verified
            and self.capture_mapping_verified
            and self.index_hint is not None
        )
        # Stages for operator UX (no raw paths)
        d["stages"] = {
            "PNP_ID_FOUND": bool(self.pnp_id_found or bool(self.stable_id.startswith("uvc:"))),
            "CAPTURE_MAPPING_VERIFIED": bool(self.capture_mapping_verified and self.mapping_verified),
            "OPENED": False,  # filled by diagnose after open
            "FRAME_RECEIVED": False,
        }
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
    # Optional DevicePath / symbolic link fingerprint (already hashed externally if needed)
    device_path_fingerprint: str = ""


CaptureLinker = Callable[[list[UsbDeviceInfo]], list[UsbDeviceInfo]]

_test_capture_linker: CaptureLinker | None = None


def set_usb_capture_linker_for_tests(linker: CaptureLinker | None) -> None:
    global _test_capture_linker
    _test_capture_linker = linker


class DirectShowEnumerator:
    """Enumerate + link Windows PnP identity to DirectShow capture *indexes*.

    Win10/11: WMI ``PNPDeviceID`` (hashed) + DirectShow moniker ordinal index.
    ``mapping_verified`` requires a unique name match that yields an integer index.
    Empty DirectShow list or missing name match ⇒ unverified (never fabricate True).
    Duplicate friendly names ⇒ ambiguous / fail-closed.
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
            return self._apply_linker(self._link_wmi_to_dshow(wmi, dshow))
        if dshow:
            out = [
                UsbDeviceInfo(
                    stable_id=fingerprint_stable_id(
                        f"dshow-name:{_norm_name(d.friendly_name)}:{d.index}"
                    ),
                    friendly_name=d.friendly_name[:128],
                    index_hint=d.index,
                    backend="dshow",
                    ambiguous=True,
                    mapping_verified=False,
                    capture_mapping_verified=False,
                    pnp_id_found=False,
                    note_vi=(
                        "Có tên DirectShow nhưng thiếu PnP hashed — không đủ CAMERA_LAB / HMAC."
                    ),
                )
                for d in dshow
            ]
            return self._apply_linker(out)
        return self._apply_linker(
            self._opencv_index_probe(
                note_vi="Không lấy được PnP ổn định — chỉ số OpenCV tạm thời; fail-closed cho LIVE."
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
                        capture_mapping_verified=False,
                        pnp_id_found=True,
                        note_vi="PnP hashed OK — chưa liên kết DirectShow index (chưa verified).",
                    )
                )
            return out
        except Exception as exc:  # noqa: BLE001
            logger.info("usb_wmi_enum_unavailable err=%s", type(exc).__name__)
            return []

    def _enumerate_dshow_named(self) -> list[_DshowNamed]:
        named = self._try_pywin32_dshow_names()
        if named:
            return named
        return self._try_opencv_index_probe_named()

    def _try_pywin32_dshow_names(self) -> list[_DshowNamed]:
        """Enumerate DirectShow video inputs via pywin32 COM (Win10/11).

        Requires optional Windows deps: pywin32 (+ WMI for PnP). Ordinal index matches
        OpenCV CAP_DSHOW open order when the system device enumerator is stable.
        """
        try:
            import pythoncom  # type: ignore
            from win32com.client import Dispatch  # type: ignore

            pythoncom.CoInitialize()
            devenum = Dispatch("SystemDeviceEnum")
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

    def _try_opencv_index_probe_named(self) -> list[_DshowNamed]:
        """Last-resort: probe openable indexes — names are placeholders, not identity."""
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
                # Placeholder name — MUST NOT uniquely verify PnP by this string alone
                out.append(_DshowNamed(index=idx, friendly_name=f"__opencv_index_{idx}__"))
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
        # WMI name collision ⇒ ambiguous even if DShow list is empty
        wmi_name_counts: dict[str, int] = {}
        for w in wmi_devs:
            k = _norm_name(w.friendly_name)
            wmi_name_counts[k] = wmi_name_counts.get(k, 0) + 1

        if not dshow:
            out: list[UsbDeviceInfo] = []
            for d in wmi_devs:
                key = _norm_name(d.friendly_name)
                dup = wmi_name_counts.get(key, 0) > 1
                out.append(
                    replace(
                        d,
                        ambiguous=bool(dup or d.ambiguous),
                        mapping_verified=False,
                        capture_mapping_verified=False,
                        index_hint=None,
                        pnp_id_found=True,
                        note_vi=(
                            "Trùng tên PnP — ambiguous; không liên kết capture."
                            if dup
                            else (
                                "PnP hashed có (PNP_ID_FOUND) nhưng DirectShow enumeration trống — "
                                "CAPTURE_MAPPING_VERIFIED=false. Cài pywin32/WMI hoặc kiểm tra driver."
                            )
                        ),
                    )
                )
            return out

        name_counts: dict[str, int] = {}
        for d in dshow:
            k = _norm_name(d.friendly_name)
            # Ignore opencv placeholder names for collision with real WMI names
            if k.startswith("__opencv_index_"):
                continue
            name_counts[k] = name_counts.get(k, 0) + 1

        out = []
        for w in wmi_devs:
            key = _norm_name(w.friendly_name)
            if wmi_name_counts.get(key, 0) > 1:
                out.append(
                    replace(
                        w,
                        ambiguous=True,
                        mapping_verified=False,
                        capture_mapping_verified=False,
                        index_hint=None,
                        pnp_id_found=True,
                        note_vi=(
                            "Nhiều thiết bị PnP cùng tên hiển thị — USB_DEVICE_AMBIGUOUS. "
                            "Không đoán index."
                        ),
                    )
                )
                continue
            matches = [
                d
                for d in dshow
                if _norm_name(d.friendly_name) == key and not key.startswith("__opencv_index_")
            ]
            if name_counts.get(key, 0) > 1 or len(matches) > 1:
                out.append(
                    replace(
                        w,
                        ambiguous=True,
                        mapping_verified=False,
                        capture_mapping_verified=False,
                        index_hint=None,
                        pnp_id_found=True,
                        note_vi="Trùng tên DirectShow — fail-closed, không mở webcam sai.",
                    )
                )
                continue
            if len(matches) == 1:
                m = matches[0]
                out.append(
                    replace(
                        w,
                        index_hint=int(m.index),
                        mapping_verified=True,
                        capture_mapping_verified=True,
                        ambiguous=False,
                        pnp_id_found=True,
                        note_vi=(
                            "CAPTURE_MAPPING_VERIFIED: PnP hashed liên kết duy nhất tới "
                            f"DirectShow index (ephemeral={m.index})."
                        ),
                    )
                )
                continue
            # No DShow name match — UNVERIFIED (do not invent video=Name trust)
            out.append(
                replace(
                    w,
                    mapping_verified=False,
                    capture_mapping_verified=False,
                    index_hint=None,
                    pnp_id_found=True,
                    note_vi=(
                        "PNP_ID_FOUND nhưng không khớp tên DirectShow — "
                        "CAPTURE_MAPPING_VERIFIED=false. Không dùng video=Name với CAP_DSHOW."
                    ),
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
                        capture_mapping_verified=False,
                        pnp_id_found=False,
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
    """Pass-through only — NEVER escalate mapping_verified from name/PnP alone.

    Trusted LIVE requires enumerator-proven DirectShow index correlation.
    """
    if dev.ambiguous:
        return replace(
            dev,
            mapping_verified=False,
            capture_mapping_verified=False,
            note_vi=dev.note_vi or "USB identity ambiguous — không escalate trust.",
        )
    if (
        bool(dev.mapping_verified)
        and bool(dev.capture_mapping_verified)
        and dev.index_hint is not None
    ):
        return dev
    # Refuse to invent verification from friendly name / PnP presence alone
    return replace(
        dev,
        mapping_verified=False,
        capture_mapping_verified=False,
        note_vi=dev.note_vi
        or "Chưa CAPTURE_MAPPING_VERIFIED — cần liên kết PnP↔DirectShow index.",
    )


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
        if not (dev.mapping_verified and dev.capture_mapping_verified):
            raise ValueError("USB_CAPTURE_UNVERIFIED")
        if dev.index_hint is None:
            raise ValueError("USB_INDEX_UNKNOWN")
    return dev


def capture_open_arg(dev: UsbDeviceInfo) -> int:
    """Integer OpenCV CAP_DSHOW index only — never FFmpeg ``video=Name`` strings."""
    if not (dev.mapping_verified and dev.capture_mapping_verified):
        raise ValueError("USB_CAPTURE_UNVERIFIED")
    if dev.index_hint is None:
        raise ValueError("USB_INDEX_UNKNOWN")
    return int(dev.index_hint)


# Back-compat helper name (must not imply FFmpeg open is valid for DSHOW)
def dshow_open_target(friendly_name: str) -> str:
    """Deprecated display helper — NOT a CAP_DSHOW open argument."""
    name = (friendly_name or "").strip()
    if not name:
        return ""
    return f"(display-only) {name}"


CaptureFactory = Callable[..., Any]
