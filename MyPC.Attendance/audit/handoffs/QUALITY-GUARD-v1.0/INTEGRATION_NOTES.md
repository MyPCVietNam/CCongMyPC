# Quality Guard v1.0 integration (PR #27 in-place)

## Overlay install

- Uploaded ZIP SHA256 `06d904a6b4b5da6c163aac61d3ce077e9de9d73939bbdd539e8aae31e2a6c707`
- All `repository-overlay/` files present at repo root (28 files; 0 missing).
- 24 identical to overlay; 4 intentionally strengthened (workflow fetch-depth, check.py,
  Pester, test_hf3_safety) for V3-additional safety — do not revert to weaker overlay.

## Baseline RED (immutable V2 freeze)

- freeze=`0ea4264440bf330f005af7447bbd6bdb6cfabb46`
- Original overlay `quality_guard/check.py --strict`: BLOCKED 3 codes
  - HF3_SYNTHETIC_FAKE_PID_REACHES_KILL_BOUNDARY
  - HF3_SYNTHETIC_RUNTIME_CALLS_REAL_STOP_PROCESS
  - HF3_PS_BACKEND_SUBSTRING_AUTHORIZATION
- `test_hf3_safety.py` (overlay): 5 FAIL / 3 PASS

## Current HEAD GREEN (V3 + V3-additional retained)

- V3 feature ancestor `97c1e9df2d54314098066eca7c88c7e82edc4c79` retained (no rewrite of fixed PID V3)
- Tip `check.py --strict`: PASS 0 codes
- `test_hf3_safety.py` (tip): 11 PASS
- Framework 4 / archive 4 / hooks 23 / independent HF3 pytest 37 PASS
- Independent review: `INDEPENDENT_REVIEW_V3ADD.md` → code-only PASS

## GitHub Actions

- tip `b4652d4`: https://github.com/MyPCVietNam/CCongMyPC/actions/runs/42355748368 — SUCCESS
  jobs: guard-contract, backend-linux, frontend, windows-contract

## Physical gates

BLOCKED (USB_WINDOWS_PHYSICAL, USB_STABILITY_30_MIN, USB_CAMERA_LAB_OWNER_SIGN, FACE_PILOT, INSTALLER, PRODUCTION_READY)
