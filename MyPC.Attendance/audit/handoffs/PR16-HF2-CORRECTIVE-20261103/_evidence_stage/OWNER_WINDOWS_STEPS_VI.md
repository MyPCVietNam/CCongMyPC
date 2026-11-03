# Owner Windows next steps (PR16-HF2)

1. Checkout HF2 tip; disposable DataDir; Python 3.12.x; FastAPI 0.115.14.
2. Frontend: `cd frontend && npm ci && npm run ci` (typecheck + vitest + build).
3. LIVE MJPEG: confirm SERVER_DECODER vs browser=UNVERIFIED/OK labels after onLoad activity.
4. Kiểm tra with LIVE up + force AUTH probe (wrong password once): handshake AUTH_FAILED, DB LIVE status preserved.
5. `python tools/audit_camera_secrets_readonly.py --data-dir <staging> --json` — expect OK or explicit INCOMPLETE (never silent zeros).
6. Lab: refresh → Tải evidence; switch kind/camera → state clears; ineligible evidence cannot click-sign.
7. Soak 15–30′ before LIVE_STABILITY claims. HMAC / FACE_PILOT / INSTALLER remain separate.
8. No production DataDir; no main merge.
