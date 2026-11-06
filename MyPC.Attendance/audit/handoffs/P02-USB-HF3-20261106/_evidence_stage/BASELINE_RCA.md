# P02-USB-HF3 — COM release / Update RCA (PR #27 in-place)

**Pre-fix PR #27 tip (this corrective):** `ff6789ecd15ede618101e6a4c4938c3290ed1748`

**Prior property-bag tip:** `05f6ba991b4b43b3719125551298b18441578bcb`

## Independent audit findings (COM-RELEASE-UPDATE handoff)

### A — BLOCKER: double COM Release
`_safe_release()` manually called `Release()` on comtypes-owned pointers. comtypes 1.4.17
`_compointer_base.__del__` also calls `Release()`. One owned reference could be released twice →
owner-Windows `Win32 exception occurred releasing IUnknown`.

**Fix:** Never manual-Release owned comtypes pointers. Drop Python refs (`var = None`) before
`CoUninitialize` on the STA worker; finalizer performs exactly-once Release. Force `gc.collect()`
before uninit so finalizers run while the apartment is alive.

### B — PS 5.1 Update Rename-Item -NewName
`Rename-Item $srcDir $backup` passed absolute paths as `-NewName`. PS 5.1 expects a leaf name.

**Fix:** Same-parent `Rename-Item -LiteralPath … -NewName $backupLeaf` / `$srcLeaf`, validate staged
backend + ZIP SHA256 before touching live `src`, refuse Update if port 18878 is unrelated-busy
(stop only verified own uvicorn), rollback on promotion/pip failure. Fake-directory unit tests
cover promote + rollback without touching a real candidate.

### C — COM_RELEASE_WARNING_COUNT frozen early
`com_release_warning_count=len(release_warnings)` was evaluated in `try` before `finally` released
`bind_ctx` / `enum_mon` / `devenum` and called `CoUninitialize`, so final cleanup warnings could
falsely report zero.

**Fix:** Hold result in `pending`; assign `com_release_warning_count=len(release_warnings)` only
after root cleanup in `finally` (Python still returns the mutated object).

## Unchanged

Strict VID+PID+MI+full-instance identity + 1:1 DevicePath↔PnP bijection. Physical USB /
CAMERA_LAB / FACE_PILOT / installer / production remain **BLOCKED** until owner evidence.
