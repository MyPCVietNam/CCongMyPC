"""Mock Camera / Replay Mode — develop without live credentials."""

from __future__ import annotations

import base64
import io
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class CameraFSM(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    AUTHENTICATED = "AUTHENTICATED"
    STREAMING = "STREAMING"
    DEGRADED = "DEGRADED"
    RECONNECTING = "RECONNECTING"


@dataclass
class DiagnosticStage:
    name: str
    status: str  # PASS|FAIL|SKIP|BLOCKED
    detail_vi: str
    sanitized_error: str = ""


@dataclass
class MockCameraState:
    fsm: CameraFSM = CameraFSM.DISCONNECTED
    mock_mode: bool = True
    frame_index: int = 0
    width: int = 640
    height: int = 360
    fps_target: float = 2.0
    last_frame_at: datetime | None = None
    host: str = ""
    stages: list[DiagnosticStage] = field(default_factory=list)


class MockCameraGateway:
    """Generates synthetic JPEG-like PNG frames without OpenCV dependency."""

    def __init__(self) -> None:
        self.state = MockCameraState()

    def connect_mock(self) -> MockCameraState:
        self.state.fsm = CameraFSM.CONNECTING
        self.state.mock_mode = True
        self.state.fsm = CameraFSM.AUTHENTICATED
        self.state.fsm = CameraFSM.STREAMING
        self.state.stages = [
            DiagnosticStage("dns_ip", "PASS", "Chế độ mô phỏng — bỏ qua DNS"),
            DiagnosticStage("onvif", "SKIP", "ONVIF không chạy ở chế độ mô phỏng"),
            DiagnosticStage("rtsp", "SKIP", "RTSP không chạy ở chế độ mô phỏng"),
            DiagnosticStage("first_frame", "PASS", "Khung hình mô phỏng sẵn sàng"),
            DiagnosticStage("stability_60s", "SKIP", "Chưa đo ổn định 60s trên camera thật"),
        ]
        return self.state

    def run_live_diagnostics(self, host: str, has_credentials: bool) -> list[DiagnosticStage]:
        """
        Staged diagnostics without claiming RTSP success.
        ONVIF-listed compatibility ≠ tested stream access.
        """
        stages: list[DiagnosticStage] = []
        self.state.host = host
        self.state.fsm = CameraFSM.CONNECTING

        if not host:
            stages.append(
                DiagnosticStage("dns_ip", "FAIL", "Chưa nhập địa chỉ IP/hostname", "MISSING_HOST")
            )
            self.state.fsm = CameraFSM.DISCONNECTED
            self.state.stages = stages
            return stages

        # Reachability probe (ICMP not always available; use TCP-ish best effort later)
        stages.append(
            DiagnosticStage(
                "dns_ip",
                "PASS" if host else "FAIL",
                f"Đã nhận địa chỉ: {host} (chưa xác nhận ICMP trong P00)",
            )
        )

        if not has_credentials:
            stages.append(
                DiagnosticStage(
                    "onvif_auth",
                    "FAIL",
                    "Thiếu thông tin đăng nhập camera (nhập trong Cài đặt bảo mật cục bộ)",
                    "MISSING_CREDENTIALS",
                )
            )
            self.state.fsm = CameraFSM.DISCONNECTED
            self.state.stages = stages
            return stages

        stages.append(
            DiagnosticStage(
                "onvif",
                "BLOCKED",
                "EZVIZ ghi nhận hỗ trợ ONVIF từ firmware V5.3.8 build 231201 — "
                "chưa kiểm chứng RTSP/ONVIF trên máy này. CAMERA_LAB_PASS chưa đạt.",
                "CAMERA_LAB_PENDING",
            )
        )
        stages.append(
            DiagnosticStage(
                "rtsp",
                "BLOCKED",
                "Không suy đoán URL RTSP (ví dụ ch1/main). Cần GetStreamUri hoặc URL thủ công từ chủ sở hữu.",
                "RTSP_UNVERIFIED",
            )
        )
        stages.append(
            DiagnosticStage(
                "first_frame",
                "BLOCKED",
                "Chưa giải mã được khung hình thật — dùng Mock Camera để tiếp tục phát triển.",
                "NO_LIVE_FRAME",
            )
        )
        self.state.fsm = CameraFSM.DISCONNECTED
        self.state.stages = stages
        return stages

    def next_frame_png_base64(self) -> dict:
        """Return a tiny synthetic PNG as base64 (no OpenCV required)."""
        self.state.frame_index += 1
        self.state.last_frame_at = datetime.now(timezone.utc)
        png = _synthetic_png(self.state.width, self.state.height, self.state.frame_index)
        return {
            "mime": "image/png",
            "width": self.state.width,
            "height": self.state.height,
            "frame_index": self.state.frame_index,
            "mock": True,
            "data_base64": base64.b64encode(png).decode("ascii"),
            "indicator_vi": "Dữ liệu mô phỏng",
        }

    def try_live_frame(self, host: str, rtsp_url: str) -> dict | None:
        """
        Attempt a genuine live decoded frame.
        Returns None when live decode is unavailable — callers must NOT substitute mock.
        P00/P01 on Linux CI: always None (CAMERA_LAB_PASS remains BLOCKED).
        """
        _ = (host, rtsp_url)
        # Live OpenCV/FFmpeg RTSP decode is Windows-lab gated; do not fake STREAMING PASS.
        self.state.fsm = CameraFSM.DISCONNECTED
        return None


def _synthetic_png(width: int, height: int, frame: int) -> bytes:
    """Minimal valid PNG without external deps (pure Python)."""
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    # RGB rows with a moving bar
    raw = bytearray()
    bar_x = frame % max(width, 1)
    for y in range(height):
        raw.append(0)  # filter none
        for x in range(width):
            # dark charcoal background + yellow accent bar
            if abs(x - bar_x) < 3:
                raw.extend((234, 179, 8))
            elif y < height // 5 and width // 3 < x < 2 * width // 3:
                # faux distant doorway region
                raw.extend((40, 44, 52))
            else:
                v = 16 + int(8 * math.sin((x + frame) * 0.05))
                raw.extend((v, v + 2, v + 4))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )
