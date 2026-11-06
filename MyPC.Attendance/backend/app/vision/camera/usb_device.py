"""Windows USB UVC device enumeration and stable identity (no secrets / no frames).

Index numbers are ephemeral. Persist ``stable_id`` only (PnP instance path or
symbolic link when available). Fail closed when identity is ambiguous.
"""

from __future__ import annotations

import hashlib
import logging
import platform
import re
from dataclasses import asdict, dataclass
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
    note_vi: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Never expose full instance path — only redacted / hashed stable_id
        d.pop("instance_path_redacted", None)
        d["stable_id_short"] = (self.stable_id[:12] + "…") if len(self.stable_id) > 12 else self.stable_id
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
    # Keep VID/PID only
    vid, pid = _parse_vid_pid(path)
    if vid and pid:
        return f"USB\\VID_{vid.upper()}&PID_{pid.upper()}\\…"
    return "USB\\…"


class DirectShowEnumerator:
    """Enumerate DirectShow video input devices via pywin32 / WMI when available.

    Falls back to OpenCV index probe (0..7) with ephemeral names — those entries
    are marked ``ambiguous=True`` and must not be persisted as stable identity.
    """

    def list_devices(self) -> list[UsbDeviceInfo]:
        if platform.system().lower() != "windows":
            return self._opencv_index_probe(note_vi="Không phải Windows — chỉ probe chỉ số OpenCV (không ổn định).")
        devices = self._try_wmi_pn_p()
        if devices:
            return devices
        devices = self._try_dshow_friendly_names()
        if devices:
            return devices
        return self._opencv_index_probe(
            note_vi="Không lấy được PnP ổn định — chỉ số OpenCV tạm thời; bắt buộc chọn lại sau cắm/rút."
        )

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
                    # Keep USB video-class devices
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
                        note_vi="Định danh PnP ổn định (hashed).",
                    )
                )
            return out
        except Exception as exc:  # noqa: BLE001
            logger.info("usb_wmi_enum_unavailable err=%s", type(exc).__name__)
            return []

    def _try_dshow_friendly_names(self) -> list[UsbDeviceInfo]:
        # Optional: OpenCV does not expose names portably; leave empty for fallback.
        return []

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
                # Ephemeral — must not be used as persisted identity
                raw = f"opencv-index:{idx}"
                out.append(
                    UsbDeviceInfo(
                        stable_id=fingerprint_stable_id(raw),
                        friendly_name=f"OpenCV camera index {idx} (tạm thời)",
                        index_hint=idx,
                        backend="dshow",
                        ambiguous=True,
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


def resolve_device(
    *,
    stable_id: str,
    enumerator: UsbEnumerator | None = None,
) -> UsbDeviceInfo:
    """Match persisted stable_id against current enumeration; fail closed if missing/ambiguous."""
    enum = enumerator or get_usb_enumerator()
    sid = (stable_id or "").strip()
    if not sid:
        raise ValueError("USB_STABLE_ID_REQUIRED")
    matches = [d for d in enum.list_devices() if d.stable_id == sid]
    if not matches:
        raise ValueError("USB_DEVICE_NOT_FOUND")
    if len(matches) > 1:
        raise ValueError("USB_DEVICE_AMBIGUOUS")
    dev = matches[0]
    if dev.ambiguous and (dev.index_hint is None):
        raise ValueError("USB_IDENTITY_UNSTABLE")
    return dev


CaptureFactory = Callable[..., Any]
