"""Strict RTSP URI policy — no credentials in URI; DNS rebind guarded; no path secrets in logs."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.validation import ValidationErrorVi, validate_camera_host
from app.vision.camera.dns_guard import resolve_and_validate_host

PRIVATE_NETS = tuple(
    ipaddress.ip_network(c) for c in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
ALLOWED_PORTS = (554, 8554, 443, 80)


@dataclass(frozen=True)
class SafeRtspEndpoint:
    scheme: str
    host: str
    port: int
    path: str
    diagnostic_label: str
    resolved_ips: tuple[str, ...] = ()


def validate_live_rtsp_uri(
    url: str,
    *,
    allowed_ports: tuple[int, ...] = ALLOWED_PORTS,
    dns_resolver=None,
    require_ipv4_literal: bool = True,
) -> SafeRtspEndpoint:
    """
    Default require_ipv4_literal=True for first reliable LIVE release (no DNS TOCTOU).
    Hostname path retained for tests via require_ipv4_literal=False + dns_resolver.
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
    if "%" in url:
        raise ValidationErrorVi("URI có percent-encoding không được hỗ trợ trong chính sách an toàn.")
    port = parsed.port if parsed.port is not None else 554
    if port not in allowed_ports:
        raise ValidationErrorVi(f"Cổng RTSP {port} ngoài danh sách cho phép.")
    host = validate_camera_host(parsed.hostname, allow_empty=False)
    if require_ipv4_literal:
        try:
            lit = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValidationErrorVi(
                "Chỉ chấp nhận IPv4 LAN literal cho RTSP v1 (chống DNS TOCTOU)."
            ) from exc
        if lit.version != 4:
            raise ValidationErrorVi("Chỉ hỗ trợ IPv4 LAN cho RTSP trong v1.")
    # Resolve + validate every A record (DNS rebinding guard). Do not swallow ValidationErrorVi.
    resolved = tuple(resolve_and_validate_host(host, resolver=dns_resolver))
    return SafeRtspEndpoint(
        scheme=parsed.scheme.lower(),
        host=host,
        port=port,
        path=parsed.path,
        diagnostic_label=f"{parsed.scheme}://{host}:{port}/<redacted>",
        resolved_ips=resolved,
    )


def pinned_rtsp_authority(endpoint: SafeRtspEndpoint) -> str:
    """Prefer first validated IPv4 so OpenCV/FFmpeg does not re-resolve hostname."""
    if not endpoint.resolved_ips:
        raise ValidationErrorVi("Thiếu IP đã ghim cho endpoint RTSP.")
    return endpoint.resolved_ips[0]


def diagnostic_rtsp_label(*, camera_id: str | int, profile: str = "MAIN") -> str:
    return f"camera_id={camera_id};profile={profile};uri=REDACTED"
