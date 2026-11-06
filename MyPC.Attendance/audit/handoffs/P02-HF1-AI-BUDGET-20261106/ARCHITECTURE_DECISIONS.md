# Architecture (P02-HF1)

## Shared budget
One monotonic interval per `camera_id` shared by JSON + mjpeg-ai + all viewers. `server_ai_fps_cap` (default 2) — clients may only lower rate.

## Single-flight
At most one detector call in flight per camera. Concurrent callers get `AI_BUSY` for their **current** frame_id (not prior cache).

## Frame identity
Never attach f1 boxes/pixels to f3 headers. Throttle/busy → `analyzed=false`, `faces=[]`. Optional annotate of current pixels with status label only.

## Overlapping race test plumbing
Unaltered audit overlapping setup relied on the budget bypass to start f2. After the fix, f2 is correctly throttled. Unit test uses `force=True` only as fixture plumbing so f2 can enter single-flight; assertions unchanged. Production paths never set force.
