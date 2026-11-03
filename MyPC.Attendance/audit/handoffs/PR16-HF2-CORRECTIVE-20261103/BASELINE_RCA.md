# PR16-HF2 Baseline RCA

**Baseline tip (PR #17 / HF1):** `78038062f57ccde20e5551fb93cdf8d58d83affd`  
**Branch:** `cursor/pr16-hf2-corrective-83a8`  
**Tree at create:** clean

## Independent audit → fixes

| ID | Finding | Fix |
|----|---------|-----|
| TS | `*,` in `diagLanes.ts` → TS1003/TS1138 | Options object API; real `tsc`/`vite`/`vitest` |
| UI | Snapshot stale overrides MJPEG LIVE | `uiStateFromLanes` viewMode + camera/gen binding |
| WD | Watchdog claimed browser freeze | `SERVER_DECODER_WATCHDOG` + `browserMjpegTransport` UNVERIFIED |
| RTSP | AUTH/404 clobbered LIVE DB status | Preserve when LIVE decoder healthy |
| SEC | Secret audit zeros without DB | INCOMPLETE + exit 3 |
| PKG | Content scan mostly ignored | Fail-closed `release_sensitive_scan` |
| PIN | `pins=None` eligible true | `eligible_for_sign=False` + reason |
| LAB | Stale evidence GET races | Gen fence; kind/camera reset |
| FPS | Corrupt pause dilutes FPS | Reset session window on corrupt streak≥3 |

Physical soak / HMAC signed / FACE_PILOT / INSTALLER remain **BLOCKED**.
