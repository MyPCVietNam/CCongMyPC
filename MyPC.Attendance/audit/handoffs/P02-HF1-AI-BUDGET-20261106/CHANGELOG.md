# P02-HF1 CHANGELOG

- `LiveFaceDetectPreviewService`: global per-camera interval across distinct `frame_id`s; server FPS cap (clients cannot raise); single-flight; `AI_THROTTLED` / `AI_BUSY` / `FRAME_NOT_ANALYZED` on **current** frame with `faces=[]`.
- Annotated MJPEG: `X-Frame-Id` / status / face count always match encoded `snap.frame_id`; skip misaligned emissions.
- CameraPage: label JSON as last-analyzed (async vs `<img>`); no false browser transport VERIFIED.
- Tests: audit repro GREEN (+ `force=True` fixture plumbing for inflight race under corrected budget); extended budget/concurrency coverage.
- Static rebuild `index-CeTofX6D.js`.
