# ADR 0001 — Approved application stack

## Status

Accepted (P00)

## Decision

Use the owner-approved open-source stack:

- go2rtc (MIT) for stream re-publish, localhost-bound
- onvif-python (MIT) for discovery; manual RTSP fallback required
- OpenCV >= 4.5 (Apache 2.0) for video/images
- YuNet (MIT) + SFace (Apache 2.0) from OpenCV Zoo — pinned SHA256
- FastAPI / Uvicorn / SQLAlchemy / Alembic / Pydantic
- React + TypeScript + Vite + Tailwind + shadcn/ui
- SQLite WAL
- openpyxl + ReportLab (PDF deferred until Vietnamese font redistributable)
- pyca/cryptography + Argon2id
- WinSW + NSIS for Windows packaging (build blocked until Windows host)

## Consequences

- No InsightFace buffalo_l or commercially-restricted model weights
- FFmpeg optional only after binary license audit; currently LICENSE_BLOCKED for packaging
- ONNX Runtime deferred until measured benefit
