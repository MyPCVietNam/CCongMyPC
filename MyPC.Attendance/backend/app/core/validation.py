"""Input validation helpers — ROI bounds, camera host/URL SSRF guards."""

from __future__ import annotations

import ipaddress
import math
import re
from urllib.parse import urlparse


class ValidationErrorVi(ValueError):
    """Vietnamese operator-facing validation error."""


_PRIVATE_OK_PREFIXES = (
    "10.",
    "192.168.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
)

# Block cloud metadata and obvious non-camera targets
_BLOCKED_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "metadata",
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
}

_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def validate_roi(x: float, y: float, w: float, h: float) -> dict[str, float]:
    for name, v in (("x", x), ("y", y), ("w", w), ("h", h)):
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValidationErrorVi(f"Tọa độ ROI {name} không hợp lệ")
        if math.isnan(v) or math.isinf(v):
            raise ValidationErrorVi(f"Tọa độ ROI {name} không được NaN/Infinity")
    if w <= 0 or h <= 0:
        raise ValidationErrorVi("Chiều rộng/cao ROI phải dương")
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        raise ValidationErrorVi("Gốc ROI phải nằm trong [0, 1]")
    if x + w > 1.0 + 1e-9 or y + h > 1.0 + 1e-9:
        raise ValidationErrorVi("ROI vượt quá khung hình (x+w hoặc y+h > 1)")
    return {"x": float(x), "y": float(y), "w": float(w), "h": float(h)}


def validate_camera_host(host: str, *, allow_empty: bool = True) -> str:
    host = (host or "").strip()
    if not host:
        if allow_empty:
            return ""
        raise ValidationErrorVi("Địa chỉ camera không được để trống")
    # Strip scheme if pasted as URL
    if "://" in host:
        raise ValidationErrorVi("Chỉ nhập IPv4/hostname — không nhập URL đầy đủ vào trường host")
    if "/" in host or "?" in host or "@" in host:
        raise ValidationErrorVi("Host camera chứa ký tự không hợp lệ")
    lower = host.lower()
    if lower in _BLOCKED_HOSTS:
        raise ValidationErrorVi("Không cho phép host loopback/metadata")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
            raise ValidationErrorVi("Không cho phép địa chỉ loopback/link-local/multicast")
        if ip.is_private:
            return host
        # Public IPs blocked by default for SSRF safety in local attendance product
        raise ValidationErrorVi(
            "Chỉ cho phép địa chỉ LAN riêng (RFC1918). IP công cộng bị chặn để chống SSRF."
        )
    except ValueError:
        pass
    # Hostname path
    if not _HOSTNAME_RE.match(host):
        raise ValidationErrorVi("Hostname camera không hợp lệ")
    if lower.endswith(".local") or host.startswith(_PRIVATE_OK_PREFIXES):
        return host
    # Allow simple LAN hostnames without dots (e.g. ezviz-cam)
    if "." not in host:
        return host
    raise ValidationErrorVi(
        "Hostname không thuộc LAN nội bộ đã được phê duyệt. Dùng IPv4 LAN hoặc hostname nội bộ."
    )


def validate_rtsp_url(url: str, *, allow_empty: bool = True) -> str:
    url = (url or "").strip()
    if not url:
        if allow_empty:
            return ""
        raise ValidationErrorVi("URL RTSP trống")
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"rtsp", "rtsps"}:
        raise ValidationErrorVi("Chỉ chấp nhận URL rtsp:// hoặc rtsps://")
    if not parsed.hostname:
        raise ValidationErrorVi("URL RTSP thiếu host")
    # Reject credentials embedded in URL for logging safety — store separately
    if parsed.username or parsed.password:
        raise ValidationErrorVi(
            "Không nhúng tài khoản/mật khẩu vào URL RTSP. Nhập riêng trong phần bảo mật."
        )
    validate_camera_host(parsed.hostname, allow_empty=False)
    if parsed.port is not None and not (1 <= parsed.port <= 65535):
        raise ValidationErrorVi("Cổng RTSP không hợp lệ")
    return url


def redact_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}{parsed.path or ''}"
