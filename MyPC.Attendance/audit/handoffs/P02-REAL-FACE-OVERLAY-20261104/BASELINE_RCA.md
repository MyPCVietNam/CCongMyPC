# P02 baseline RCA

## Observation (owner 2026-11-04)
EZVIZ LIVE works in isolated Windows staging; YuNet/SFace REAL ready; CAMERA_LAB signed. CameraPage showed raw MJPEG + numeric ROI fields only — no painted face boxes / ROI rectangles, so operators could not visually validate detection or ROI placement. LIVE badge = decoder only, not AI.

## Gap
No server path ran `detect_and_quality` for operator preview with frame-aligned overlays; no GET regions; UI default ROI could override saved DB values silently.

## Fix
Shared detect cache + JSON + annotated MJPEG on same `frame_id`; GET regions; CameraPage opt-in overlay; ROI draft/save semantics; preserve CAMERA_LAB on ROI edit.
