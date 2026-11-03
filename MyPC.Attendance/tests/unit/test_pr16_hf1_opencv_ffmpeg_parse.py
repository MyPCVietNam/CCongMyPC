"""PR16-HF1: parse FFmpeg YES/NO from OpenCV build info."""

from app.api.health import parse_opencv_ffmpeg_backend


def test_ffmpeg_yes_line():
    build = "General configuration:\n\n  Video I/O:\n    FFMPEG:                      YES\n    GStreamer:                   NO\n"
    r = parse_opencv_ffmpeg_backend(build)
    assert r["ffmpeg_backend"] == "YES"
    assert r["ffmpeg_yes"] is True


def test_ffmpeg_no_line():
    build = "  Video I/O:\n    FFMPEG:                      NO\n"
    r = parse_opencv_ffmpeg_backend(build)
    assert r["ffmpeg_backend"] == "NO"
    assert r["ffmpeg_yes"] is False


def test_ffmpeg_unknown_when_only_word_mention():
    build = "This build mentions FFMPEG libraries somewhere without YES/NO line"
    r = parse_opencv_ffmpeg_backend(build)
    assert r["ffmpeg_backend"] == "unknown"
    assert r["ffmpeg_yes"] is None


def test_ffmpeg_empty_unknown():
    r = parse_opencv_ffmpeg_backend("")
    assert r["ffmpeg_backend"] == "unknown"
