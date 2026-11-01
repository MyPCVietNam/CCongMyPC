"""Camera gateway package — Live RTSP / recorded / mock with distinct provenance."""

from app.vision.camera.gateway import (
    AuthorizedRecordedVideoGateway,
    CameraFrame,
    CameraGateway,
    LiveRTSPGateway,
    MockFrameGateway,
    StreamProvenance,
)

__all__ = [
    "AuthorizedRecordedVideoGateway",
    "CameraFrame",
    "CameraGateway",
    "LiveRTSPGateway",
    "MockFrameGateway",
    "StreamProvenance",
]
