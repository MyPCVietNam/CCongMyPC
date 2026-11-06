# P02-HF1 RCA

## Baseline
PR #22 tip `d0a6b3cf3c974e6ac953db16efce5393e3d4cbd2`.

## P1 — budget bypass
Cache throttle required `cached.frame_id == frame.frame_id`, so new LIVE frames at ~20 FPS each triggered YuNet. Fixed: throttle by last inference monotonic time regardless of frame_id; server FPS cap.

## P1 — cross-frame identity
In-flight path returned prior cached snapshot/annotated BGR; MJPEG labeled `X-Frame-Id` from the newer source frame. Fixed: busy/throttle placeholders use **current** frame_id + empty faces; MJPEG emits only when `snap.frame_id == fr.frame_id`.
