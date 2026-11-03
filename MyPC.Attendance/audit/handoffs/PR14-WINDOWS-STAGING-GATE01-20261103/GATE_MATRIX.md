# Windows Staging Gate 01 — PASS / FAIL / BLOCKED

**Repo:** MyPCVietNam/CCongMyPC  
**PR:** #14 (`cursor/pr13-release-safety-83a8`)  
**Baseline HEAD:** `956ec4d8d11fc4e6eecc755d2fed8ae7943c4ec7`  
**Feature:** `43c87f469d09b97bd345d082e6a916a2299bb351`  
**Evidence date (Asia/Bangkok):** 2026-11-03  

Legend:
- **PASS (independent / cloud pinned)** — reproduced here on Python 3.12.3 + FastAPI 0.115.14
- **PASS (reported)** — claimed by prior Cursor handoff; cited but not solely relied on
- **PASS (independent audit)** — third-party audit zip (may use different Python/FastAPI)
- **OWNER WINDOWS** — must be run on owner staging PC/VM
- **BLOCKED** — missing physical Windows/EZVIZ/installer environment; **not** claimed PASS

| ID | Gate | Result | Evidence |
|----|------|--------|----------|
| SRC-01 | PR #14 HEAD = baseline | PASS (cloud) | `git rev-parse` = `956ec4d…` |
| SRC-02 | ZIP path scanner clean | PASS (cloud + audit) | `logs/scanner_clean_zips.txt` |
| SRC-03 | Independent audit ZIP/manifest SHA | PASS (audit) | `reports/INDEPENDENT_AUDIT_REPORT_VI.md` |
| SEC-01 | New release ZIPs exclude data/secrets | PASS | scanner PASS |
| SEC-02 | Historic public ZIP exposure containment | OWNER ACTION OPEN | `CREDENTIAL_EXPOSURE_INVENTORY_VI.md` |
| SEC-03 | Git history rewrite | OWNER ACTION OPEN — **not performed** | `GIT_HISTORY_REMEDIATION_PROPOSAL_VI.md` |
| INS-01 | Fresh empty DataDir → HEAD 0012 | PASS (cloud pinned) | `logs/INSTALL_SQLITE_GATE.txt` |
| INS-02 | Second boot idempotent | PASS (cloud pinned) | same |
| INS-03 | Unknown legacy fail-closed | PASS (cloud pinned) | same |
| INS-04 | Synthetic pre-0010 upgrade preserves camera/secret | PASS (cloud) | same; **not** genuine prod clone |
| INS-05 | Genuine old DataDir upgrade + rollback drill | OWNER WINDOWS / BLOCKED here | `OWNER_CHECKLIST_INSTALL_UPGRADE_VI.md` |
| TX-01 | C01–C12, C14 + A01/A02 focus | PASS (cloud pinned) | `logs/pytest_c01_c14_focus.txt` (22 passed) |
| TX-02 | Flush-fault staged cleanup | PASS (cloud) | included in followups / 295 suite |
| C13-01 | HTTP 503 `SECRET_FS_OUTBOX_INCOMPLETE` on FastAPI 0.115.14 | PASS (cloud pinned) | `logs/C13_WIRE_RESPONSE_REDACTED.txt` |
| C13-02 | Outbox durable + retry → pending=0 | PASS (cloud pinned) | same |
| C13-03 | Same C13 on **Windows** ASGI/service | OWNER WINDOWS | checklist |
| RT-01 | Full pytest pinned runtime | PASS (cloud) | `logs/pytest_full_pinned_runtime.txt` **295 passed** |
| RT-02 | Independent unit (FastAPI 0.128 env) | PASS (audit reported) | 181 passed / 4 skipped — C13 N/A on that env |
| CAM-01 | CAMERA_LAB EZVIZ RTSP/HEVC | **BLOCKED** | `OWNER_CHECKLIST_CAMERA_LAB_VI.md` |
| FACE-01 | FACE_PILOT consented subjects | **BLOCKED** | `OWNER_CHECKLIST_FACE_PILOT_VI.md` |
| EXIT-01 | EXIT_VERIFICATION v1.5 windows | **BLOCKED** | same camera/face docs |
| INST-01 | Windows installer install/upgrade/rollback | **BLOCKED** | `OWNER_CHECKLIST_INSTALLER_VI.md` |

## Decision

| Scope | Decision |
|-------|----------|
| Source / clean packaging | **PASS** — proceed to disposable Windows staging |
| Cloud pinned regression (3.12.3 / 0.115.14) | **PASS** — 295 tests + C13 wire |
| Disposable Windows staging | **CONDITIONAL GO** — owner runs checklists |
| Live DataDir / main merge / physical PASS labels | **HOLD / BLOCKED** |

No merge of PR #12/#13/#14 to main. No production DataDir changes. No CAMERA_LAB / FACE_PILOT / EXIT / INSTALLER marked PASS.
