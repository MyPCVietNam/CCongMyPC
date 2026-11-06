"""Camera gateway package — Live RTSP / USB UVC / recorded / mock with distinct provenance."""

from app.vision.camera.gateway import (
    AuthorizedRecordedVideoGateway,
    CameraFrame,
    CameraGateway,
    LiveRTSPGateway,
    MockFrameGateway,
    StreamProvenance,
)
from app.vision.camera.usb_uvc_gateway import LiveUsbUvcGateway

__all__ = [
    "AuthorizedRecordedVideoGateway",
    "CameraFrame",
    "CameraGateway",
    "LiveRTSPGateway",
    "LiveUsbUvcGateway",
    "MockFrameGateway",
    "StreamProvenance",
]
