# P02-HF1 acceptance

| Item | Result |
|------|--------|
| Baseline audit repros RED on P02 | PASS (recorded) |
| Budget across distinct frame_ids (calls≤1) | PASS |
| Overlapping never returns old frame as current | PASS |
| Extended f1/f2/f3, concurrent clients, cache, clear, rev | PASS |
| MJPEG header/pixel frame_id alignment | PASS |
| ROI PUT does not revoke CAMERA_LAB / rotate config_rev | PASS (unchanged) |
| pytest 419 / vitest 13 / typecheck / build | PASS |
| Physical soak / LIVE_STABILITY / FACE_PILOT / installer / prod | **BLOCKED** |
