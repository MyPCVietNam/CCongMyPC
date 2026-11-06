# P02-USB-HF3 — Root cause

## Patch (identity false-positive on PR #27 tip `bab8127`)

Independent audit reproduced 3/4 RED in `test_p02_usb_hf3_identity_boundary.py`:

1. `capture_instances_match` used substring containment (`na in nb`) → distinct instances `A&ONE` vs `A&ONE2` matched.
2. VID/PID + trailing-instance fallback ignored MI → `MI_00` matched `MI_01`.
3. Linker then set `mapping_verified=True` / ephemeral index to the **wrong** camera.

**Fix:** strict `parse_usb_video_function_id` equality (VID|PID|MI|full instance). No containment, no MI-blind fallback. 1:1 bijection required.

## Original HF3 (vs PR #26)

`Dispatch('SystemDeviceEnum')` → `CO_E_CLASSSTRING` (0x800401F3); fixed via `CoCreateInstance(ICreateDevEnum)`.

## Rollback

- Identity patch: revert to `bab8127` only if needed (not recommended).
- Full HF3: PR #26 tip `146d04c`. Do not mutate owner DataDirs / 18876 / 18877.
