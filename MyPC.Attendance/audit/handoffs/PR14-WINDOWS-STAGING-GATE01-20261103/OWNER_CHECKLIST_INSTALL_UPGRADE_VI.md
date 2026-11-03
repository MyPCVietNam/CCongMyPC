# Checklist owner — Cài mới / nâng cấp / C13 (Windows staging)

**Máy:** VM/PC staging riêng. **Cấm** DataDir production.  
**HEAD cần xác minh:** `956ec4d8d11fc4e6eecc755d2fed8ae7943c4ec7`  
**Runtime mục tiêu:** Python 3.12.3, `fastapi==0.115.14` (hoặc lock đã kiểm thử trong `>=0.115,<0.116`).

## A. Chuẩn bị

- [ ] `git fetch` + `git checkout` đúng commit PR #14; ghi `git rev-parse HEAD` vào `RUNTIME_VERSIONS.txt`
- [ ] `python --version` → 3.12.x
- [ ] `pip install -r MyPC.Attendance/backend/requirements.txt` rồi `pip show fastapi` → 0.115.x; `pip check`
- [ ] Tạo thư mục DataDir **mới** (A) và (tuỳ chọn) clone disposable (B) — xem mục B
- [ ] App lắng nghe port riêng; không trỏ production

## B. Sao chép DataDir an toàn (cho upgrade)

- [ ] **Dừng** dịch vụ MyPC trên máy nguồn
- [ ] Copy đủ: `*.sqlite3`, `-wal`, `-shm`, cả cây `secrets/`, face templates, key files, giữ ACL
- [ ] **Không** upload clone lên GitHub/ChatGPT/email
- [ ] Chỉ dùng mật khẩu/camera giả khi test phá hủy trên clone

## C. NEW INSTALL (DataDir A rỗng)

- [ ] Khởi động app với DataDir A
- [ ] `GET /api/v1/health` → `alembic_ok=true`, `fastapi_supported=true`, ghi `fastapi_version`
- [ ] SQL: `SELECT version_num FROM alembic_version;` → `20261103_0012`
- [ ] `PRAGMA integrity_check;` → `ok`
- [ ] Tắt/bật lại app (SECOND BOOT) — không lỗi duplicate column/table; user bootstrap còn

## D. UPGRADE (DataDir B clone)

- [ ] Ghi nhận trước: số camera, employee, attendance, enrollment/template (chỉ số đếm, không xuất PII)
- [ ] Khởi động app trỏ B; chờ migrate
- [ ] `alembic_version` = `20261103_0012`; integrity `ok`
- [ ] Số đếm sau ≥ trước (không mất hàng); đọc được secret camera synthetic/lab
- [ ] Thử DB có bảng nhưng **không** có `alembic_version` trên bản copy riêng → phải `alembic_ok=false`, không auto-stamp

## E. Rollback drill

- [ ] Giữ backup nguyên vẹn trước upgrade
- [ ] (Tuỳ chọn) cố tình hỏng migrate trên bản throwaway → khôi phục từ backup → app chạy lại được
- [ ] Không thử phá trên production

## F. C13 trên Windows (bắt buộc trước khi tin runtime)

Dùng **clone** + credential giả:

- [ ] Login admin; tạo camera MOCK với password giả
- [ ] Inject lỗi promote (hoặc dùng script `scripts/Invoke-C13FaultSmoke.ps1` nếu có) sau commit SQL
- [ ] Phản hồi HTTP **503**, JSON `detail.code` = `SECRET_FS_OUTBOX_INCOMPLETE`
- [ ] Kiểm `pending_count` > 0 trên diagnostics/outbox (redact log)
- [ ] `POST /api/v1/system/secret-fs-outbox/retry` (SETTINGS_APPLY + CSRF) hoặc restart → `pending_count=0`
- [ ] Lưu `C13_WIRE_RESPONSE_REDACTED.txt` (xoá cookie/token/password)

## G. C11 / C12 / C14 smoke

- [ ] C11: không gọi scrub/retry admin trong lúc REPLACE chưa commit nếu nghi ngờ bản cũ
- [ ] C12: PATCH name/host + REPLACE — metadata giữ
- [ ] C14: hard-delete camera rồi tạo mới (id có thể trùng) — secret mới không bị DELETE cũ xóa

## Kết quả ghi nhận

| Mục | PASS/FAIL | Ghi chú |
|-----|-----------|---------|
| NEW INSTALL | | |
| SECOND BOOT | | |
| UPGRADE clone | | |
| C13 Windows | | |
| C11/C12/C14 smoke | | |
