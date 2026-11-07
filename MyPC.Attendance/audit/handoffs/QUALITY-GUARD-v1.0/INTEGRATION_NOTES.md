# Quality Guard v1.0 integration (PR #27 in-place)

## Baseline RED (immutable V2 freeze)

- freeze=`0ea4264440bf330f005af7447bbd6bdb6cfabb46`
- `quality_guard/check.py --strict`: BLOCKED 3 codes
  - HF3_SYNTHETIC_FAKE_PID_REACHES_KILL_BOUNDARY
  - HF3_SYNTHETIC_RUNTIME_CALLS_REAL_STOP_PROCESS
  - HF3_PS_BACKEND_SUBSTRING_AUTHORIZATION
- `test_hf3_safety.py`: 5 FAIL / 3 PASS
- independent V3 suite on V2 scripts: 6 FAIL

## Current HEAD GREEN (V3 already present)

- V3 feature ancestor `97c1e9df2d54314098066eca7c88c7e82edc4c79` retained (no rewrite)
- `check.py --strict`: PASS 0 codes
- guard unittest discover: 16 PASS
- independent V3 suite: 6 PASS
- framework/hook/archive selftests: PASS

## GitHub Actions

- workflows API returned total_count=0 before push of this workflow file
- After push: expect jobs guard-contract, backend-linux, frontend, windows-contract
- Until Actions runs appear on the commit: label **UNRUN** (do not claim PASS)

## Physical gates

BLOCKED (USB_WINDOWS_PHYSICAL, USB_STABILITY_30_MIN, USB_CAMERA_LAB_OWNER_SIGN, FACE_PILOT, INSTALLER, PRODUCTION_READY)
