# PR16-HF3 acceptance matrix

| Item | Result | Notes |
|------|--------|-------|
| Stale PHYSICAL + revoked/REJECTED lab run not eligible | PASS | unit repro |
| Nonexistent lab_run_id not eligible / POST 422 | PASS | unit + REST |
| Rejected / expired / wrong kind / config mismatch rejected | PASS | integration |
| Fresh PHYSICAL + matching config/pins signs; verify OK | PASS | integration |
| Post-sign evidence/lab revoke closes active gate | PASS | live relational; signature retained |
| Reconfigure revokes evidence audit marker | PASS | integration |
| RBAC PILOT_APPROVE + CSRF preserved | PASS | existing + HF3 REST |
| No checkbox / auto FACE_PILOT / PRODUCTION_READY | PASS | unchanged deny paths |
| Frontend sign race fence (POST/GET switch) | PASS | vitest deferred Promises |
| Browser MJPEG onLoad ≠ LIVE_STABILITY_PASS | PASS | UNVERIFIED without multipart proof |
| pytest full suite | PASS | 379 passed |
| frontend typecheck + vitest + build/ci | PASS | |
| Windows physical / soak / HEVC / owner HMAC / FACE_PILOT / INSTALLER / production | BLOCKED | owner camera OFF |
