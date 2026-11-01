# P02Q Windows Lab Readiness

## Status: BLOCKED / NOT_RUN for physical gates

This agent did **not** reach the company Windows PC or EZVIZ H8 Pro on LAN.

## Ready for owner

1. Script: `scripts/windows/Test-MyPCCamera.ps1` (updated P02Q steps: DECODED_MEASURED, AUTO_TEST_ONLY, evening/IR).
2. App path: Camera → Gắn nguồn LIVE (URI **without** password) → Đo chất lượng ảnh → So sánh nhận diện (shadow).
3. Confirm preview `provenance=CAMERA_LIVE`, `size_source=DECODED_MEASURED`, `camera_lab_pass=false` until signed.
4. Record native `width×height`, measured FPS, face width/inter-eye at marked entrance spot for DAY/DUSK/NIGHT_IR.
5. TCP PASS ≠ RTSP decode PASS. Replay/MOCK ≠ CAMERA_LAB PASS.

## Still blocked

| Gate | Reason |
|------|--------|
| CAMERA_LAB | No physical decode evidence |
| FACE_PILOT | No held-out LIVE volunteer/negative set |
| WINDOWS installer | Not built/tested on Windows here |
| Exit AUTO | Person detector license BLOCKED |
