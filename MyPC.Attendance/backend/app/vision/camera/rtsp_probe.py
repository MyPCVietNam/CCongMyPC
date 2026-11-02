"""Bounded, sanitized RTSP staged probe — no password logging / no brute force."""

from __future__ import annotations

import base64
import socket
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


CANDIDATE_PATHS_DOCUMENTED = (
    # Labeled manual profiles only — NOT auto-bruteforced
    {"path": "/ch1/main", "label": "EZVIZ FAQ (C6N/TY1/TY2) — chưa xác minh H8 Pro"},
    {"path": "/h264/ch1/main/av_stream", "label": "Một số firmware EZVIZ cũ"},
    {"path": "/Streaming/Channels/101", "label": "Kiểu Hikvision-compatible (nếu firmware hỗ trợ)"},
)


@dataclass
class ProbeStage:
    name: str
    status: str  # PASS|FAIL|UNKNOWN|SKIPPED
    detail_vi: str
    code: str = ""


@dataclass
class RtspProbeResult:
    camera_id: int
    config_revision: str
    overall_status: str
    stages: list[ProbeStage] = field(default_factory=list)
    camera_lab_pass: bool = False
    secrets_redacted: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "config_revision": self.config_revision,
            "overall_status": self.overall_status,
            "stages": [s.__dict__ for s in self.stages],
            "camera_lab_pass": False,
            "secrets_redacted": True,
            "candidate_paths_documented": list(CANDIDATE_PATHS_DOCUMENTED),
            "note_vi": (
                "TCP mở ≠ LIVE. 401 = xác thực; 404 = đường dẫn/endpoint. "
                "Không tự dò mật khẩu/đường dẫn. CAMERA_LAB vẫn BLOCKED."
            ),
        }


def _read_rtsp_response(sock: socket.socket, limit: int = 4096) -> str:
    sock.settimeout(4.0)
    chunks: list[bytes] = []
    total = 0
    while total < limit:
        try:
            part = sock.recv(512)
        except socket.timeout:
            break
        if not part:
            break
        chunks.append(part)
        total += len(part)
        if b"\r\n\r\n" in b"".join(chunks):
            break
    return b"".join(chunks).decode("latin-1", errors="replace")


def _classify_rtsp_status(text: str) -> tuple[str, str]:
    upper = text.upper()
    if "401" in text[:80] or "UNAUTHORIZED" in upper:
        return "AUTH_FAILED", "RTSP trả 401 Unauthorized (thách thức/xác thực thất bại)."
    if "404" in text[:80] or "NOT FOUND" in upper:
        return "STREAM_NOT_FOUND", "RTSP trả 404 Not Found (đường dẫn/stream không tồn tại)."
    if "200" in text[:80] or "RTSP/1.0 200" in upper:
        return "OK", "RTSP DESCRIBE/OPTIONS nhận 200."
    if not text.strip():
        return "UNKNOWN", "Không nhận được phản hồi RTSP có thể phân loại."
    return "UNKNOWN", "Phản hồi RTSP không phân loại được chắc chắn (không lộ nội dung nhạy cảm)."


def probe_rtsp_stages(
    *,
    camera_id: int,
    config_revision: str,
    host: str,
    port: int,
    path: str,
    username: str | None,
    password: str | None,
    try_auth: bool,
) -> RtspProbeResult:
    result = RtspProbeResult(
        camera_id=camera_id,
        config_revision=config_revision or "",
        overall_status="UNKNOWN",
    )
    if not host:
        result.stages.append(
            ProbeStage("TCP_REACHABILITY", "FAIL", "Thiếu host/IP camera.", "NO_HOST")
        )
        result.overall_status = "UNKNOWN"
        return result

    # 1) TCP
    try:
        with socket.create_connection((host, int(port or 554)), timeout=3.0) as sock:
            result.stages.append(
                ProbeStage(
                    "TCP_REACHABILITY",
                    "PASS",
                    f"TCP {host}:{port} reachable — chưa phải decode LIVE.",
                    "TCP_OK",
                )
            )
            # 2) OPTIONS without auth
            req = (
                f"OPTIONS rtsp://{host}:{port}{path or '/'} RTSP/1.0\r\n"
                f"CSeq: 1\r\n"
                f"User-Agent: MyPCAttendanceProbe/1.0\r\n"
                f"\r\n"
            )
            sock.sendall(req.encode("ascii", errors="ignore"))
            resp = _read_rtsp_response(sock)
            code, detail = _classify_rtsp_status(resp)
            result.stages.append(
                ProbeStage("RTSP_OPTIONS", "PASS" if code == "OK" else "FAIL", detail, code)
            )
    except OSError as exc:
        result.stages.append(
            ProbeStage(
                "TCP_REACHABILITY",
                "FAIL",
                f"Không kết nối TCP được ({type(exc).__name__}).",
                "TCP_FAIL",
            )
        )
        result.overall_status = "RTSP_DISABLED_OR_UNAVAILABLE"
        return result

    # 3) DESCRIBE — once without auth, optionally once with Basic if try_auth
    def _describe(with_auth: bool) -> ProbeStage:
        try:
            with socket.create_connection((host, int(port or 554)), timeout=3.0) as sock:
                headers = (
                    f"DESCRIBE rtsp://{host}:{port}{path or '/'} RTSP/1.0\r\n"
                    f"CSeq: 2\r\n"
                    f"Accept: application/sdp\r\n"
                    f"User-Agent: MyPCAttendanceProbe/1.0\r\n"
                )
                if with_auth and username is not None:
                    token = base64.b64encode(
                        f"{username}:{password or ''}".encode("utf-8")
                    ).decode("ascii")
                    headers += f"Authorization: Basic {token}\r\n"
                headers += "\r\n"
                sock.sendall(headers.encode("ascii", errors="ignore"))
                resp = _read_rtsp_response(sock)
                code, detail = _classify_rtsp_status(resp)
                name = "RTSP_DESCRIBE_AUTH" if with_auth else "RTSP_DESCRIBE"
                st = "PASS" if code == "OK" else "FAIL"
                return ProbeStage(name, st, detail, code)
        except OSError as exc:
            return ProbeStage(
                "RTSP_DESCRIBE_AUTH" if with_auth else "RTSP_DESCRIBE",
                "FAIL",
                f"Lỗi kết nối khi DESCRIBE ({type(exc).__name__}).",
                "CONNECT_FAIL",
            )

    stage = _describe(False)
    result.stages.append(stage)
    if try_auth and username:
        # Single authenticated attempt — never loop/guess
        result.stages.append(_describe(True))

    # Aggregate
    codes = {s.code for s in result.stages}
    if "AUTH_FAILED" in codes and "OK" not in codes:
        result.overall_status = "AUTH_FAILED"
    elif "STREAM_NOT_FOUND" in codes and "AUTH_FAILED" not in codes:
        result.overall_status = "STREAM_NOT_FOUND"
    elif any(s.name.startswith("RTSP_DESCRIBE") and s.code == "OK" for s in result.stages):
        result.overall_status = "CONFIG_SAVED"  # handshake ok ≠ decoded frame
        result.stages.append(
            ProbeStage(
                "FIRST_DECODED_FRAME",
                "UNKNOWN",
                "Handshake RTSP có tín hiệu — chưa đo khung hình giải mã trên bước probe này.",
                "WAITING_FOR_FRAME",
            )
        )
    else:
        result.overall_status = "UNKNOWN"
    return result


def parse_rtsp_parts(uri: str) -> tuple[str, int, str]:
    p = urlparse(uri or "")
    host = p.hostname or ""
    port = int(p.port or 554)
    path = p.path or "/"
    return host, port, path
