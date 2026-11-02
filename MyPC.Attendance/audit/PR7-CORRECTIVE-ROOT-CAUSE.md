# PR7 Corrective — Root Causes

| ID | Fix |
|----|-----|
| E01 | Branch fingerprint scripts; tests run on PR7/corrective tip (167 PASS), not P00 |
| E02 | Client AB → `UNTRUSTED_IMPORT`; AUTO_VALIDATED requires PHYSICAL + APPROVED + `can_auto_enable` |
| E03 | CAMERA_LAB/FACE_PILOT require `evidence_id` PHYSICAL_VERIFIED; checkbox rejected |
| E04 | HMAC verify compares kind/approval_id/issuer/pins/AB/evidence/expiry vs row |
| E05 | Config mismatch invalidation commits on independent session before 409 |
| E06 | Pins include YuNet+SFace+margin+min_face policy digest |
| E07 | Gallery revision hashes embedding ciphertext/bytes |
| E08 | Health/report: `settings_flag_*` vs `camera_lab_pass`/`signed_camera_lab` |
| E09/E10 | Windows API diagnostic script + model provisioning doc; gates stay BLOCKED |
