# Freeze vs tip
- baseline = P02 tip `d0a6b3c…`
- feature = HF1 code commit
- packaging_freeze (PACKAGE_META) = tree used to build ZIPs (manifest HEAD)
- packaging_freeze_sidecar = ZIP-introducing commit
- remote_pr_tip = after push (docs sidecars; ZIP bytes unchanged)
Pre-freeze FEATURE/FREEZE placeholders are overwritten before packaging; frozen ZIP does not contain future tip hashes.
