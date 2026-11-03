# PR16 Baseline RCA — RealCam stability / HEVC / status honesty

**Baseline branch:** `cursor/pr14-camera-staged-acl-83a8`  
**HEAD verified:** `684ba74dac23af46e735c62204ebd8b49e863589`  
**Feature ACL:** `527fcb993d5182b9d758c8940678aec412ed1a0f`  
**Tree:** clean at branch create · PR16 branch `cursor/pr16-realcam-stability-83a8`

## Owner Windows facts (accepted, not re-disputed)

- EZVIZ H8 Pro LIVE MJPEG works; ~2880×1620; ~19.7 FPS; `provenance=CAMERA_LIVE`
- Lab: PHYSICAL_VERIFIED evidence exists; `camera_lab_pass=false` until HMAC (by design)
- FFmpeg stderr shows HEVC `cu_qp_delta` / missing POC ref warnings
- Probe/UI still show CONFIG_SAVED / BLOCKED / MOCK badge while LIVE works
- Staging secret counts: 1 camera, 4 live files, 3 staged (audit required; no auto-delete)

## Evidence-backed software issues

| ID | Symptom | Root cause (code evidence) | Fix in PR16 |
|----|---------|----------------------------|-------------|
| S1 | MOCK header while LIVE MJPEG | `App.tsx` fetches runtime-badge only on `[user]` | Poll/refetch badge; prefer ready LIVE source |
| S2 | RTSP test → CONFIG_SAVED clobbers mental model of LIVE | `test_rtsp` sets `row.connection_status = result.overall_status` even on handshake OK (`CONFIG_SAVED`) | Persist handshake separately; don't treat handshake as LIVE; leave DB status unless AUTH/404 |
| S3 | FIRST_FRAME BLOCKED while decoded | Probe is handshake-only; UI conflates lanes | Label HANDSHAKE_ONLY; decoder lane from runtime |
| S4 | HEVC stderr vs corrupt counter | No FFmpeg stderr capture; `hevc_ref_events` is **image-stat heuristic** only | Telemetry honesty: `native_decoder_error_category=UNAVAILABLE`; rename/clarify; A/B owner tools |
| S5 | Corrupt path hot-loop | `_loop` `continue` after corrupt with no sleep | Bounded sleep/backoff on corrupt streak |
| S6 | Preview can look OK while reconnecting | `get_latest_frame` ignores gateway `_status` | Overlay STALE/RECONNECTING from gateway status |
| S7 | HMAC not reachable in Lab UI | WindowsLab ends at promote; never `POST .../quality/approvals` | Add PILOT_APPROVE signing step; no bypass |
| S8 | Staged secret counts opaque | No read-only inventory tool | Read-only auditor (paths/counts only) |

## Non-claims

- Cannot assert FFmpeg POC stderr ≡ `hevc_ref_events` without native log plumbing (UNAVAILABLE).
- Cannot mark CAMERA_LAB_SIGNED / LIVE_STABILITY_PASS / FACE_PILOT from cloud.
- Will not rotate credentials or rewrite Git history.

## Physical gates

CAMERA_LAB HMAC · FACE_PILOT · INSTALLER · long soak = **BLOCKED** until owner Windows evidence.
