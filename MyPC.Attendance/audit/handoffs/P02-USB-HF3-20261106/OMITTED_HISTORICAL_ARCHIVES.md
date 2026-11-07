# Historical archive ZIP omission (FULL-SOURCE hygiene)

FULL-SOURCE intentionally **excludes** binary `.zip` delivery archives (and `.onnx` / data / secrets).
Tracked `SHA256SUMS*.txt` under older handoff folders still list SHA256 digests for those
omitted delivery ZIPs. Those digests are **custody records of past deliveries**, not a claim
that this FULL-SOURCE tree contains or re-verifies the binary archives.

- Do **not** rewrite historical hashes.
- Do **not** report “all historical manifests verified” against this tree.
- Current delivery authenticity is only: this package’s `SHA256SUMS.txt` /
  `SHA256SUMS-COMPLETE.txt` for the four ZIPs built at `packaging_freeze_commit`.
- Quarantine stubs under `audit/QUARANTINE_PUBLIC_ARCHIVES/*.QUARANTINED.txt` document
  intentionally withheld public archives.

Count of tracked `SHA256SUMS*.txt` files that reference `.zip` names: see
`tools/package_p02_usb_hf3_complete_audit.py` note in `PACKAGE_META.json` field
`historical_zip_digests_omitted_from_full_source`.
