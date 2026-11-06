# P02-USB-HF2 changelog

## Corrective on PR #25 (`6d1842b`)

- Stop fabricating `mapping_verified` from PnP name / empty DShow.
- Distinguish `PNP_ID_FOUND` vs `CAPTURE_MAPPING_VERIFIED` vs `OPENED` vs `FRAME_RECEIVED`.
- Ban OpenCV CAP_DSHOW opens via FFmpeg `video=Name`; index-only after verified mapping.
- Clear stale gateway index on mapping loss; fail closed on identity mismatch.
- Pin Windows enum deps in `requirements-windows.txt`.
- Working candidate script `p02_usb_hf2_candidate_18878.ps1` (Prepare/Preflight/Start/Export).
- UI diagnose shows stage flags; enumerate copy no longer suggests video=Name.
- Regression suite `test_p02_usb_hf2_trust_and_open_regressions.py` + script contract tests.
