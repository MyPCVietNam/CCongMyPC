# P02-USB-HF2 — Root cause analysis (baseline PR #25)

**Baseline:** `6d1842b5c2bd577f4945f35e85767228906fae0d` (PR #25 tip, `cursor/p02-usb-hf1-stable-bind-83a8`)

## P0-A — Fabricated `mapping_verified`

| Location | Defect |
|----------|--------|
| `usb_device.enrich_for_capture()` | Escalated `mapping_verified=False` → `True` solely because a non-ambiguous PnP record had a friendly name. |
| `usb_device._link_wmi_to_dshow()` | Marked PnP devices `mapping_verified=True` when DirectShow enumeration was empty or unmatched. Duplicate friendly names were not always fail-closed when DShow was missing. |

**Fix:** Never escalate trust from PnP presence alone. Empty/unmatched DShow → explicit unverified + user-facing reason. Duplicate names → ambiguous even without DShow. Trusted LIVE requires `capture_mapping_verified` + unique integer index.

## P0-B — FFmpeg `video=Name` via CAP_DSHOW

| Location | Defect |
|----------|--------|
| `usb_uvc_gateway._default_open_capture` | Called `cv2.VideoCapture(target, CAP_DSHOW)` with string targets. OpenCV DSHOW is index-based; `video=Name` is FFmpeg syntax. |
| `requirements.txt` | No Windows enumeration dependency; optional `wmi`/`win32com` paths were pretend-complete. |

**Fix:** Reject non-integer open targets for DSHOW. Open only verified DirectShow indices. Pin `requirements-windows.txt` (pywin32 + WMI). Stages: `PNP_ID_FOUND` / `CAPTURE_MAPPING_VERIFIED` / `OPENED` / `FRAME_RECEIVED`. Physical Windows verification remains **BLOCKED**.

## P0-C — Stale index after disconnect

| Location | Defect |
|----------|--------|
| `LiveUsbUvcGateway._reresolve_index` | Later enumeration with `index_hint=None` left old `self._index`, risking reopen of a different webcam after USB reorder. |

**Fix:** Clear `_index` / open_target before re-resolve. Missing/ambiguous mapping → OFFLINE/BLOCKED; no last-good frame reuse. Same verified USB identity keeps `config_revision`; material change revokes per existing lifecycle.

## P1-D — Candidate script never started backend

| Location | Defect |
|----------|--------|
| `p02_usb_hf1_candidate_18878.ps1 -Mode Start` | Logged and exited; never launched uvicorn. Models copied without `MYPC_MODELS_DIR`. |

**Fix:** New `p02_usb_hf2_candidate_18878.ps1` — Prepare (venv + pins + SHA256 ZIP), Preflight, Start (uvicorn on `127.0.0.1:18878`), Export (redacted ZIP). Sets `MYPC_DATA_DIR` / `MYPC_MODELS_DIR`. Does not touch 18876/18877.

## Rollback

Reset to PR #25 tip `6d1842b`. Do not mutate owner DataDirs.
