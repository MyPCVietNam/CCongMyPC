# Owner acceptance matrix — PR13 release safety

| ID | Gate | Result | Evidence |
|----|------|--------|----------|
| SEC-01 | Contaminated FULL ZIPs removed from tree + quarantine notices | PASS | `audit/QUARANTINE_PUBLIC_ARCHIVES/`, `*.zip.QUARANTINED.md` |
| SEC-02 | Allowlisted packaging (git ls-files) + nested ZIP scanner | PASS | `tools/package_clean_source_zips.py`, `tools/sensitive_path_scanner.py` |
| SEC-03 | New FULL/CHANGED ZIPs scan PASS (no data/secrets/keys/sqlite) | PASS | scanner report + SHA256SUMS |
| SEC-04 | Owner history rewrite + credential rotation | **OWNER** | Agent cannot rewrite public history unilaterally |
| INS-01 | Empty DataDir → alembic_ok=True, HEAD 0012 | PASS | `test_clean_install_migrates_to_head_and_survives_second_boot` |
| INS-02 | Second boot idempotent at same HEAD | PASS | same test |
| INS-03 | Upgrade pre-0010/0011 preserves camera + secrets + integrity | PASS | `test_upgrade_pre_0010_preserves_camera_and_integrity` |
| INS-04 | Unknown legacy (tables, no alembic_version) fails closed | PASS | `test_unknown_legacy_db_fails_closed_without_auto_stamp` |
| CLN-01 | Flush fault leaves live secret; staged+lease gone | PASS | `test_failed_outbox_flush_leaves_no_staged_blob_or_lease` |
| C13-01 | FastAPI 0.115.x pin verified | PASS | `reports/runtime-pin.txt`, `test_fastapi_version_gate_matches_requirements` |
| C13-02 | Promote failure → HTTP 503 SECRET_FS_OUTBOX_INCOMPLETE + durable outbox | PASS | `test_postcommit_fs_failure_must_return_real_http_503`, `test_c13_asgi_and_fastapi_pin` |
| C01–C14 | Prior outbox/lifecycle fixes preserved | PASS | `test_pr13_independent_regressions.py` |
| PHYS | CAMERA_LAB / FACE_PILOT / EXIT / INSTALLER | **BLOCKED** | No Windows/EZVIZ evidence this run |

## Counts

- Pytest: 295 passed (Python 3.12.3, FastAPI 0.115.14)
- FAIL: 0 in supported runtime
