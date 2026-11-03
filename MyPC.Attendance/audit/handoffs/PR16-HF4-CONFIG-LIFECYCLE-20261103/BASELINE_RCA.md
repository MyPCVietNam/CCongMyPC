# PR16-HF4 RCA

## Baseline
PR #19 tip `9c5e706b1f8290bfff5f0182a910e371614ee9c0` (HF3). Independent audit ZIP `MYPC-PR16-HF3-AUDIT-HF4-HANDOFF`.

## P0-A
`PATCH /cameras/{id}` could change host/RTSP/credentials/mock without rotating `config_revision` or revoking PHYSICAL evidence/lab/HMAC. HF3 revision checks could not see silent source drift.

## P1-B
Empty provenance and NULL `expires_at` were accepted. Fail closed now (`EVIDENCE_PROVENANCE_INVALID`, `LAB_RUN_PROVENANCE_INVALID`, `LAB_RUN_EXPIRY_MISSING`).

## P1-C
Lab challenge TTL (`RUN_TTL_HOURS=8`) must not shorten a 30-day HMAC after PHYSICAL promotion. Policy: NULL expiry fails; challenge TTL applies to in-progress runs; PHYSICAL_VERIFIED trust follows revoke/config/pins/approval TTL.

## P1-D
`AUTO_VALIDATED` verification now re-requires active CAMERA_LAB + FACE_PILOT under the same pins/camera.
