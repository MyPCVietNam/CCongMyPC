# PR6 Follow-up — Root Cause Fixes

## A01 / A09 — SQLite UTC + HMAC drift

**Cause:** Aware `now` vs SQLite-naive `expires_at`; `isoformat()` offset lost after rehydrate → HMAC mismatch.

**Fix:** `app/core/utc_time.py` canonical Zulu (`…Z`); `issue_approval` signs stored `payload_json`; `verify_active_approval` verifies that payload (not recomputed row fields). Naive DB values treated as UTC. Ambiguous timestamps fail closed.

## A02 / A10 — AUTO_VALIDATED without evidence

**Cause:** Client-supplied pins signed; empty pins skipped; settings flags short-circuited checks.

**Fix:** Server-derived pins (`server_pins.derive_live_pins`); AUTO_VALIDATED requires DB `ab_run_id` with samples, plus camera-bound CAMERA_LAB + FACE_PILOT; migration demotes unsigned AUTO_VALIDATED → AUTO_TEST_ONLY; `verify_active_approval(require_pins=True)` fail-closed.

## A03 — Enrollment camera rebind

**Cause:** `camera_id` not persisted; `/frame` trusted client camera_id / base64 as LIVE.

**Fix:** Alembic `0006` + `EnrollmentSession` binding fields; REAL_CAMERA start requires signed CAMERA_LAB for that camera + LIVE registry; frames use server-bound camera only; DEMO≠LIVE; client images rejected on LIVE sessions; config revision mismatch invalidates session.

## A04 / A05 — Empty gallery labeled OK

**Cause:** `gallery=[]`; synthetic mode returned `OK`.

**Fix:** `gallery_loader` + analyze-once/observe-shadow load ACTIVE templates; paired statuses: `BLOCKED_GALLERY` / `DEMO_SYNTHETIC` / `BLOCKED_MODEL` / `REAL_VALIDATION`.

## A06 — DNS TOCTOU

**Cause:** Hostname validated then OpenCV re-resolved.

**Fix:** LIVE configure defaults to IPv4 LAN literal; capture URI uses pinned IP (`pinned_rtsp_authority`).
