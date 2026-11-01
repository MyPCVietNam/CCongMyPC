# P01.5-HF Security Report

## Fixed: plaintext embeddings in `progress_json` (HIGH)

**Before:** `face_embeddings[slot] = vec.tolist()` persisted in SQLite.  
**After:** progress JSON only holds non-sensitive metadata via `scrub_progress()`. Identity consistency decrypts `EnrollmentSample.encrypted_embedding` in RAM (`_ram_embeddings` / `_load_slot_embeddings`), never written back to DB.

Migration `20261102_0003_p015_hf_scrub_progress` removes forbidden keys from existing rows. **Not secure deletion** of WAL/backups — see `P015-HF-DATA-CLEANUP.md`.

## Fixed: DEMO→AUTO provenance mixup

Enrollment `source` preserved (`DEMO` stays `DEMO`). Separate `capture_origin` (`SYNTHETIC_TEST` / `AUTHORIZED_UPLOAD` / `CAMERA_LIVE`).

## Fixed: production fixture / force_slot bypass

`AppSettings.synthetic_fixtures_allowed()` / `force_slot_allowed()` are **false** in production. API returns **403** `SYNTHETIC_FIXTURE_DENIED` even for `ENROLLMENT_MANAGE`.

## Body references

DEMO/`testing_mode` stores AES-GCM `encrypted_image` crops. Outside testing_mode, synthetic person detector yields `BODY_DETECTOR_NOT_READY` / `BODY_CAPTURE_BLOCKED` instead of fake PASS.

## Residual risks

- Historical DBs/backups may still contain old plaintext vectors until reviewed/rotated.
- Live RTSP credentials handled in-process; OS process inspection limitations remain — never log URIs with userinfo.
- go2rtc optional and disabled by default; must not bind to LAN.
