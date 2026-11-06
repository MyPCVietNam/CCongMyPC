"""Windows USB UVC device enumeration and stable identity (no secrets / no frames).

Persist hashed ``stable_id`` only (PnP instance path). OpenCV indexes are ephemeral.
``mapping_verified`` / ``capture_mapping_verified`` require a unique DirectShow
**DevicePath** correlated to that PnP video function — never FriendlyName alone,
VID/PID alone, empty DShow lists, or ProgID Automation Dispatch of the
System Device Enumerator (CO_E_CLASSSTRING).
"""

from __future__ import annotations

import hashlib
import logging
import platform
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Callable, Protocol

from app.vision.camera.dshow_com_enum import (
    DshowVideoMoniker,
    capture_instances_match,
    enumerate_video_capture_monikers,
    get_last_dshow_enum_result,
    redacted_enum_diagnostics,
)

logger = logging.getLogger(__name__)

SOURCE_TYPE_USB_UVC = "USB_UVC"
SOURCE_TYPE_RTSP = "RTSP"

_AUDIO_NAME_RE = re.compile(
    r"(microphone|\bmic\b|audio|speaker|headset|headphone)",
    re.I,
)


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
    pnp_id_found: bool = False
    capture_mapping_verified: bool = False
    device_path_fingerprint: str = ""
    note_vi: str = ""
    # Internal raw PnP for DevicePath match — NEVER exposed via to_public_dict
    _pnp_raw: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("instance_path_redacted", None)
        d.pop("_pnp_raw", None)
        d["stable_id_short"] = (self.stable_id[:12] + "…") if len(self.stable_id) > 12 else self.stable_id
        d["trusted_live_eligible"] = bool(
            (not self.ambiguous)
            and self.mapping_verified
            and self.capture_mapping_verified
            and self.index_hint is not None
            and bool(self.device_path_fingerprint)
        )
        d["stages"] = {
            "PNP_ID_FOUND": bool(self.pnp_id_found or bool(self.stable_id.startswith("uvc:"))),
            "CAPTURE_MAPPING_VERIFIED": bool(
                self.capture_mapping_verified and self.mapping_verified and self.device_path_fingerprint
            ),
            "OPENED": False,
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


def _is_audio_function_name(name: str) -> bool:
    n = name or ""
    if not _AUDIO_NAME_RE.search(n):
        return False
    # "UGREEN Camera 4K" is video; "UGREEN Camera 4K Audio" / Microphone are not
    if re.search(r"camera|webcam|imaging", n, re.I) and not re.search(
        r"(audio|microphone|\bmic\b)", n, re.I
    ):
        return False
    return True


def _is_video_pnp_candidate(name: str, pnp: str, pnp_class: str = "") -> bool:
    if _is_audio_function_name(name):
        return False
    cls = (pnp_class or "").strip().lower()
    if cls in {"media", "audioendpoint", "sound", "audio"}:
        return False
    if cls in {"camera", "image", "imagingdevices"}:
        return True
    low = name.lower()
    if "camera" in low or "webcam" in low or "imaging" in low:
        return True
    if "usb\\vid_" in pnp.lower() and "video" in low:
        return True
    return False


@dataclass(frozen=True)
class _DshowNamed:
    index: int
    friendly_name: str
    device_path: str = ""
    device_path_fingerprint: str = ""


CaptureLinker = Callable[[list[UsbDeviceInfo]], list[UsbDeviceInfo]]

_test_capture_linker: CaptureLinker | None = None


def set_usb_capture_linker_for_tests(linker: CaptureLinker | None) -> None:
    global _test_capture_linker
    _test_capture_linker = linker


class DirectShowEnumerator:
    """Enumerate + link Windows PnP video identity to DirectShow capture indexes.

    Verification requires unique DevicePath ↔ PnP instance match. FriendlyName is UI only.
    OpenCV CAP_DSHOW index = VideoInputDeviceCategory moniker ordinal when mapping proven.
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
                        f"dshow-path:{d.device_path_fingerprint or d.index}"
                    ),
                    friendly_name=d.friendly_name[:128],
                    index_hint=d.index,
                    backend="dshow",
                    ambiguous=True,
                    mapping_verified=False,
                    capture_mapping_verified=False,
                    pnp_id_found=False,
                    device_path_fingerprint=d.device_path_fingerprint,
                    note_vi=(
                        "Có DirectShow video moniker nhưng thiếu PnP hashed — "
                        "không đủ CAMERA_LAB / HMAC."
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
                pnp_class = str(getattr(cam, "PNPClass", "") or "")
                if not name or not pnp:
                    continue
                if not _is_video_pnp_candidate(name, pnp, pnp_class):
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
                        note_vi="PnP video hashed OK — chưa liên kết DirectShow DevicePath.",
                        _pnp_raw=pnp,
                    )
                )
            return out
        except Exception as exc:  # noqa: BLE001
            logger.info("usb_wmi_enum_unavailable err=%s", type(exc).__name__)
            return []

    def _enumerate_dshow_named(self) -> list[_DshowNamed]:
        """Native COM video monikers — never Dispatch('SystemDeviceEnum')."""
        result = enumerate_video_capture_monikers()
        out: list[_DshowNamed] = []
        for m in result.monikers:
            out.append(
                _DshowNamed(
                    index=int(m.ordinal),
                    friendly_name=(m.friendly_name or "")[:128],
                    device_path=m.device_path,
                    device_path_fingerprint=m.device_path_fingerprint,
                )
            )
        if out:
            return out
        # Do NOT fall back to OpenCV index probe as "named" identity — that fabricates names.
        return []

    def _link_wmi_to_dshow(
        self, wmi_devs: list[UsbDeviceInfo], dshow: list[_DshowNamed]
    ) -> list[UsbDeviceInfo]:
        wmi_name_counts: dict[str, int] = {}
        for w in wmi_devs:
            k = _norm_name(w.friendly_name)
            wmi_name_counts[k] = wmi_name_counts.get(k, 0) + 1

        last = get_last_dshow_enum_result()
        empty_reason = (
            (last.detail_vi if last else "")
            or "DirectShow video enumeration trống / thất bại."
        )

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
                        device_path_fingerprint="",
                        pnp_id_found=True,
                        note_vi=(
                            "Trùng tên PnP video — ambiguous; không liên kết capture."
                            if dup
                            else (
                                "PNP_ID_FOUND nhưng DSHOW_VIDEO_MONIKER_COUNT=0 — "
                                f"CAPTURE_MAPPING_VERIFIED=false. {empty_reason}"
                            )
                        ),
                    )
                )
            return out

        # DevicePath uniqueness among monikers
        path_counts: dict[str, int] = {}
        for d in dshow:
            if d.device_path_fingerprint:
                path_counts[d.device_path_fingerprint] = (
                    path_counts.get(d.device_path_fingerprint, 0) + 1
                )

        # Pre-compute strict DevicePath↔PnP matches; require 1:1 bijection
        # (one WMI video function ↔ one DirectShow moniker).
        provisional: list[tuple[UsbDeviceInfo, list[_DshowNamed]]] = []
        moniker_claim_counts: dict[str, int] = {}
        for w in wmi_devs:
            pnp_raw = getattr(w, "_pnp_raw", "") or ""
            matches = [
                d
                for d in dshow
                if d.device_path
                and pnp_raw
                and capture_instances_match(d.device_path, pnp_raw)
            ]
            provisional.append((w, matches))
            for m in matches:
                fp = m.device_path_fingerprint or f"ord:{m.index}"
                moniker_claim_counts[fp] = moniker_claim_counts.get(fp, 0) + 1

        out = []
        for w, matches in provisional:
            key = _norm_name(w.friendly_name)
            if wmi_name_counts.get(key, 0) > 1:
                out.append(
                    replace(
                        w,
                        ambiguous=True,
                        mapping_verified=False,
                        capture_mapping_verified=False,
                        index_hint=None,
                        device_path_fingerprint="",
                        pnp_id_found=True,
                        note_vi=(
                            "Nhiều thiết bị PnP video cùng tên hiển thị — USB_DEVICE_AMBIGUOUS. "
                            "Không đoán index / không tin FriendlyName."
                        ),
                    )
                )
                continue

            pnp_raw = getattr(w, "_pnp_raw", "") or ""
            # Missing DevicePath on all candidates that might name-match → unverified
            if not pnp_raw:
                out.append(
                    replace(
                        w,
                        mapping_verified=False,
                        capture_mapping_verified=False,
                        index_hint=None,
                        device_path_fingerprint="",
                        pnp_id_found=True,
                        note_vi="Thiếu PnP raw nội bộ để khớp DevicePath — fail-closed.",
                    )
                )
                continue

            if not matches:
                # Name-only correlation is explicitly NOT verification
                out.append(
                    replace(
                        w,
                        mapping_verified=False,
                        capture_mapping_verified=False,
                        index_hint=None,
                        device_path_fingerprint="",
                        pnp_id_found=True,
                        note_vi=(
                            "PNP_ID_FOUND nhưng không khớp DirectShow DevicePath "
                            "(CAPTURE_MAPPING_UNVERIFIED). FriendlyName không đủ định danh. "
                            "Không dùng video=Name với CAP_DSHOW."
                        ),
                    )
                )
                continue

            if len(matches) > 1:
                out.append(
                    replace(
                        w,
                        ambiguous=True,
                        mapping_verified=False,
                        capture_mapping_verified=False,
                        index_hint=None,
                        device_path_fingerprint="",
                        pnp_id_found=True,
                        note_vi="Nhiều DevicePath khớp cùng PnP — fail-closed.",
                    )
                )
                continue

            m = matches[0]
            claim_key = m.device_path_fingerprint or f"ord:{m.index}"
            if moniker_claim_counts.get(claim_key, 0) > 1:
                out.append(
                    replace(
                        w,
                        ambiguous=True,
                        mapping_verified=False,
                        capture_mapping_verified=False,
                        index_hint=None,
                        device_path_fingerprint="",
                        pnp_id_found=True,
                        note_vi=(
                            "Nhiều PnP video khớp cùng một DirectShow DevicePath — "
                            "không 1:1; CAPTURE_MAPPING_UNVERIFIED."
                        ),
                    )
                )
                continue
            if not m.device_path_fingerprint:
                out.append(
                    replace(
                        w,
                        mapping_verified=False,
                        capture_mapping_verified=False,
                        index_hint=None,
                        device_path_fingerprint="",
                        pnp_id_found=True,
                        note_vi="DevicePath trống / không fingerprint — CAPTURE_MAPPING_UNVERIFIED.",
                    )
                )
                continue
            if path_counts.get(m.device_path_fingerprint, 0) > 1:
                out.append(
                    replace(
                        w,
                        ambiguous=True,
                        mapping_verified=False,
                        capture_mapping_verified=False,
                        index_hint=None,
                        device_path_fingerprint="",
                        pnp_id_found=True,
                        note_vi="Trùng DevicePath fingerprint giữa các moniker — fail-closed.",
                    )
                )
                continue

            out.append(
                replace(
                    w,
                    index_hint=int(m.index),
                    mapping_verified=True,
                    capture_mapping_verified=True,
                    ambiguous=False,
                    pnp_id_found=True,
                    device_path_fingerprint=m.device_path_fingerprint,
                    note_vi=(
                        "CAPTURE_MAPPING_VERIFIED: PnP video ↔ DirectShow DevicePath duy nhất; "
                        f"OpenCV CAP_DSHOW index tạm={m.index} (ephemeral, không phải identity)."
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
    """Pass-through only — NEVER escalate mapping_verified from name/PnP alone."""
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
        and bool(dev.device_path_fingerprint)
    ):
        return dev
    return replace(
        dev,
        mapping_verified=False,
        capture_mapping_verified=False,
        note_vi=dev.note_vi
        or "Chưa CAPTURE_MAPPING_VERIFIED — cần PnP↔DirectShow DevicePath duy nhất.",
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
        if not dev.device_path_fingerprint:
            raise ValueError("USB_DEVICE_PATH_UNVERIFIED")
        if dev.index_hint is None:
            raise ValueError("USB_INDEX_UNKNOWN")
    return dev


def capture_open_arg(dev: UsbDeviceInfo) -> int:
    """Integer OpenCV CAP_DSHOW index only — never FFmpeg ``video=Name`` strings."""
    if not (dev.mapping_verified and dev.capture_mapping_verified):
        raise ValueError("USB_CAPTURE_UNVERIFIED")
    if not dev.device_path_fingerprint:
        raise ValueError("USB_DEVICE_PATH_UNVERIFIED")
    if dev.index_hint is None:
        raise ValueError("USB_INDEX_UNKNOWN")
    return int(dev.index_hint)


def dshow_open_target(friendly_name: str) -> str:
    """Deprecated display helper — NOT a CAP_DSHOW open argument."""
    name = (friendly_name or "").strip()
    if not name:
        return ""
    return f"(display-only) {name}"


def usb_redacted_diagnostics() -> dict[str, Any]:
    """Aggregate redacted USB enum diagnostics for owner scripts / SafeExport."""
    diag = redacted_enum_diagnostics()
    try:
        devices = get_usb_enumerator().list_devices()
    except Exception:
        devices = []
    verified = [d for d in devices if d.capture_mapping_verified and d.mapping_verified]
    return {
        **diag,
        "PNP_VIDEO_COUNT": sum(1 for d in devices if d.pnp_id_found),
        "VIDEO_DEVICE_PATH_MATCH_COUNT": len(verified),
        "CAPTURE_MAPPING_VERIFIED": bool(verified),
        "VERIFIED_INDEX": verified[0].index_hint if len(verified) == 1 else None,
        "trusted_live_eligible_count": sum(
            1 for d in devices if d.to_public_dict().get("trusted_live_eligible")
        ),
    }


CaptureFactory = Callable[..., Any]
