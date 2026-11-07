# P02-USB-HF3 changelog

## Patch on PR #27 — venv redirector PID ownership (in-place)

- Verified descendant listener ownership for 18878.
- Launch meta JSON; Stop/Update share trust model; no foreign kills.
- Health: `ok` + `READY` only; ownership failures not swallowed.
- Unit matrix: `tests/unit/test_p02_usb_hf3_pid_ownership.py`.

## Prior — VT_BSTR direct Read / CoInit / COM release / Update leaf rename / identity

Retained.
