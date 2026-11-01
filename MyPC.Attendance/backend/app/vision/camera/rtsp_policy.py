"""Strict RTSP URI policy — no credentials in URI; no path/query secrets in logs."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.validation import ValidationErrorVi, validate_camera_host

PRIVATE_NETS = tuple(
    ipaddress.ip_network(c) for c in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
ALLOWED_PORTS = (554, 8554, 443, 80)  # common RTSP / tunnel; still LAN-only hosts


@dataclass(frozen=True)
class SafeRtspEndpoint:
    scheme: str
    host: str
    port: int
    path: str
    # Never include username/password/query/fragment
    diagnostic_label: str  # camera_id/profile only style label later


def validate_live_rtsp_uri(url: str, *, allowed_ports: tuple[int, ...] = ALLOWED_PORTS) -> SafeRtspEndpoint:
    """
    Production live URI policy:
    - rtsp/rtsps only
    - no userinfo (credentials stored separately)
    - no query/fragment (tokens often leak there)
    - path required, limited length, no backslash
    - host must pass validate_camera_host (LAN)
    - literal private IPv4 preferred; hostnames allowed only via validate_camera_host
    """
    if not isinstance(url, str) or not url or len(url) > 1024 or url.strip() != url:
        raise ValidationErrorVi("URI RTSP không hợp lệ (độ dài/khoảng trắng).")
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in url):
        raise ValidationErrorVi("URI RTSP chứa ký tự điều khiển bị cấm.")
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise ValidationErrorVi("Cấu trúc URI RTSP không hợp lệ.") from exc
    if parsed.scheme.lower() not in {"rtsp", "rtsps"}:
        raise ValidationErrorVi("Chỉ chấp nhận rtsp:// hoặc rtsps://")
    if not parsed.hostname:
        raise ValidationErrorVi("URI RTSP thiếu host.")
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        raise ValidationErrorVi(
            "Không nhúng tài khoản/mật khẩu vào URI. Lưu credential riêng (mã hóa)."
        )
    if parsed.query or parsed.fragment or "?" in url or "#" in url:
        raise ValidationErrorVi(
            "Cấm query/fragment trên URI RTSP (dễ chứa token bí mật)."
        )
    if not parsed.path.startswith("/") or len(parsed.path) > 160 or "\\" in parsed.path:
        raise ValidationErrorVi("Đường dẫn stream RTSP không hợp lệ.")
    # Conservative: reject percent-encoding to avoid decoding tricks
    if "%" in url:
        raise ValidationErrorVi("URI có percent-encoding không được hỗ trợ trong chính sách an toàn.")
    port = parsed.port if parsed.port is not None else 554
    if port not in allowed_ports:
        raise ValidationErrorVi(f"Cổng RTSP {port} ngoài danh sách cho phép.")
    host = validate_camera_host(parsed.hostname, allow_empty=False)
    # Extra: if literal IP, must be RFC1918 (not loopback/link-local/public)
    try:
        ip = ipaddress.ip_address(host)
        if ip.version != 4 or not any(ip in net for net in PRIVATE_NETS):
            raise ValidationErrorVi("Địa chỉ IP phải thuộc RFC1918 (LAN nội bộ).")
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
            raise ValidationErrorVi("Địa chỉ IP bị cấm (loopback/link-local/multicast).")
    except ValueError:
        # hostname path already validated by validate_camera_host
        pass
    return SafeRtspEndpoint(
        scheme=parsed.scheme.lower(),
        host=host,
        port=port,
        path=parsed.path,
        diagnostic_label=f"{parsed.scheme}://{host}:{port}/<redacted>",
    )


def diagnostic_rtsp_label(*, camera_id: str | int, profile: str = "MAIN") -> str:
    """Safe export label — never a usable URI."""
    return f"camera_id={camera_id};profile={profile};uri=REDACTED"
