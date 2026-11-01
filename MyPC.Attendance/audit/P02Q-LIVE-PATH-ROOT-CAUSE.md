# P02Q LIVE Path Root Cause + Fixes

Baseline audited: PR #4 `42c75d3…`

## P0-A LIVE disconnect — FIXED

| Finding | Location (PR #4) | Fix |
|---------|------------------|-----|
| `POST …/gateway/live/configure` set `state.camera_gateway` | `api/cameras.py` | Bind into `CameraSourceRegistry` keyed by DB `camera_id` |
| `GET …/{id}/preview` used `state.camera.try_live_frame` → `LIVE_NOT_IMPLEMENTED` | `api/cameras.py` | Preview reads **same** bound gateway; mock only when `mock_mode` and unbound |
| Silent MOCK risk for live cams | preview | Live unbound → `503 LIVE_NOT_CONFIGURED` (no DEMO substitute) |

## P0-B RTSP policy — FIXED

| Finding | Fix |
|---------|-----|
| configure used `startswith("rtsp")` only | `vision/camera/rtsp_policy.py` `validate_live_rtsp_uri` |
| Credentials/query/path leakage | Reject userinfo/query/fragment/%-encoding; response uses `diagnostic_rtsp_label` / REDACTED |
| `sanitize_rtsp_for_log` left path | Now strips path; exports use camera_id/profile only |
| `validate_rtsp_url` weaker | Delegates to same live policy |

## P0-C mutable BGR — FIXED

| Finding | Fix |
|---------|-----|
| `CameraFrame.bgr` writable shared ndarray | `_seal()` copy + `write=False`; `clone_pixels()` for consumers |
| Preview mutate risk | Preview resizes a clone only |

## P0-D telemetry honesty — FIXED

| Finding | Fix |
|---------|-----|
| `fps_estimate` unused | Rolling monotonic receive FPS in `LiveRTSPGateway.health()` |
| CAP_PROP as truth | `size_source=DECODED_MEASURED` only after `frame.shape`; else `UNVERIFIED` |
| `_dropped` as network loss | Exposed as `overwritten_latest` / `dropped_frames` app-level overwrite |

## P0-E lifecycle — FIXED

| Finding | Fix |
|---------|-----|
| Non-idempotent `start()` | Guard with alive-thread check |
| Stale frames after reconfig | `bind()` syncs `config_revision`, clears `_latest`; preview rejects revision mismatch |
| Shutdown | FastAPI shutdown stops registry gateways |

## P0-F person detector — UNCHANGED / BLOCKED

YOLOX / real person detector remains **BLOCKED** (license/weights). Exit verification & AUTO overtime stay TIMEKEEPER review. Does not block camera-quality diagnostics.

## Config revision sync bug found during implementation

`BoundSource.config_revision` was a new UUID while `LiveRTSPGateway`/`MockFrameGateway` kept a different init UUID → preview would 409. **Fixed** in `registry.bind()` by assigning the bound revision onto the gateway before publishing frames; configure binds **before** `start()`.
