# PR11-HF Root Cause

**Base:** `7f9040556f29b1a7d44aa5b2014a453c8cc1026c` (PR #11)  
**Branch:** `cursor/pr11-camera-rtsp-hf-83a8`

| Defect | Cause | Fix |
|--------|-------|-----|
| Cannot edit/delete cameras | UI POST-only; no GET/PATCH/archive | Full CRUD + archive/restore/delete |
| Form not reloaded on select | `selected` independent of `form` | `GET /cameras/{id}` loads safe fields into form |
| Blank password wipes secret | `if username or password: put(..., password="")` | Explicit `credential_action` keep/replace/remove |
| LIVE claimed without frames | configure returned success after start() | `CONFIG_SAVED` / `live_verified=false` until frames_ok |
| Infinite RTSP spam | unbounded reconnect loop | max 8 attempts → STOPPED; per-camera unbind |
| Mixed 401/404 noise | multiple bound cameras | stop/archive unbinds; logs include camera_id |
| Hard delete risk | no dependency preflight | archive default; hard delete blocked by history |
