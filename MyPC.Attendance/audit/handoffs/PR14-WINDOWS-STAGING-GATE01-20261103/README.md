# PR14 — Windows Staging Gate 01 Evidence

Baseline GitHub HEAD: `956ec4d8d11fc4e6eecc755d2fed8ae7943c4ec7`  
Đối chiếu audit độc lập đính kèm + mã nguồn tại tip PR #14.

## Nội dung

| Path | Mô tả |
|------|--------|
| `GATE_MATRIX.md` | PASS/FAIL/BLOCKED từng cổng |
| `STAGING_SMOKE_MATRIX.md` | Ma trận smoke |
| `logs/` | Runtime pin, install/upgrade, C13 redact, pytest — **không** secret |
| `OWNER_CHECKLIST_*.md` | Hướng dẫn tiếng Việt cho owner |
| `CREDENTIAL_EXPOSURE_INVENTORY_VI.md` | Inventory đường dẫn lộ (không giá trị) |
| `GIT_HISTORY_REMEDIATION_PROPOSAL_VI.md` | Đề xuất rewrite — **chưa chạy** |
| `OPEN_ISSUES_AND_NEXT_STEPS_VI.md` | Việc còn lại |
| `reports/` | Bản audit độc lập (tham chiếu) |
| `scripts/` | Helper PowerShell capture |

## Phân loại kết quả

- **PASS (cloud pinned):** Python 3.12.3 + FastAPI 0.115.14 trên agent Linux.
- **OWNER WINDOWS / BLOCKED:** Cần máy Windows / EZVIZ / installer — không giả lập PASS.

## Cấm

Không merge main; không đụng DataDir production; không gắn CAMERA_LAB/FACE_PILOT/EXIT/INSTALLER = PASS từ gói này.
