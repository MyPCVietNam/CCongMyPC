"""DNS resolution allowlist for RTSP hosts — reject rebinding to non-LAN."""

from __future__ import annotations

import ipaddress
import socket
from typing import Iterable

from app.core.validation import ValidationErrorVi

DEFAULT_ALLOWED_CIDRS = (
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
)


def _allowed_nets(cidrs: Iterable[str]) -> list[ipaddress.IPv4Network]:
    return [ipaddress.ip_network(c, strict=False) for c in cidrs]


def resolve_and_validate_host(
    host: str,
    *,
    allowed_cidrs: tuple[str, ...] = DEFAULT_ALLOWED_CIDRS,
    resolver=None,
) -> list[str]:
    """
    Resolve A/AAAA and require EVERY address in allowlisted private CIDRs.
    Literal IPs are checked without DNS. IPv6 currently rejected (no allowlist).
    """
    nets = _allowed_nets(allowed_cidrs)
    try:
        lit = ipaddress.ip_address(host)
        if lit.version != 4:
            raise ValidationErrorVi("Chỉ hỗ trợ IPv4 LAN cho RTSP trong v1.")
        if not any(lit in n for n in nets):
            raise ValidationErrorVi("IP đích ngoài VLAN/CIDR được phép.")
        if lit.is_loopback or lit.is_link_local or lit.is_multicast or lit.is_unspecified:
            raise ValidationErrorVi("IP bị cấm (loopback/link-local/multicast).")
        return [str(lit)]
    except ValueError:
        pass

    resolve = resolver or socket.getaddrinfo
    try:
        infos = resolve(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValidationErrorVi("Không phân giải được hostname camera.") from exc
    if not infos:
        raise ValidationErrorVi("Hostname camera không có bản ghi DNS.")
    addrs: list[str] = []
    for info in infos:
        sockaddr = info[4]
        ip_s = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_s)
        except ValueError as exc:
            raise ValidationErrorVi("Địa chỉ DNS không hợp lệ.") from exc
        if ip.version != 4:
            raise ValidationErrorVi("Bản ghi IPv6 bị từ chối (chưa allowlist).")
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or not any(ip in n for n in nets):
            raise ValidationErrorVi(
                "DNS rebinding / đích ngoài LAN bị chặn — hostname phân giải ngoài CIDR cho phép."
            )
        addrs.append(str(ip))
    # Deduplicate preserving order
    out: list[str] = []
    for a in addrs:
        if a not in out:
            out.append(a)
    return out
