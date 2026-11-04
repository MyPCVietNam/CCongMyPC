# Architecture decisions (P02)

## Annotated MJPEG (opt-in) + JSON metadata
Boxes are drawn on the **same** cloned native frame that is JPEG-encoded for `/preview/mjpeg-ai`. JSON `/live/face-detect` shares the cache keyed by camera+frame_id. Original smooth MJPEG remains untouched.

## No second RTSP capture
Uses `camera_registry.get_frame` only (CAMERA_LIVE, reject MOCK, max_age 5s).

## No synthetic as REAL
If `inference_mode != REAL` or detector not ready → `NOT_READY` with empty faces (no fabricated boxes).

## ROI gate
ROI save invalidates exit spatial calibration only; **does not** revoke CAMERA_LAB HMAC or rotate `config_revision`.

## Privacy
Detection+quality only; `identity_exposed=false`; no embeddings/similarity in overlay payloads.
