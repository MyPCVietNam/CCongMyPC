# MyPC Attendance — Audit độc lập PR #14 (Release Safety)

**Ngày:** 2026-11-03  
**Repo:** https://github.com/MyPCVietNam/CCongMyPC  
**PR:** https://github.com/MyPCVietNam/CCongMyPC/pull/14  
**HEAD GitHub xác minh:** `956ec4d8d11fc4e6eecc755d2fed8ae7943c4ec7`  
**Base:** `aee02e8c515237b38adf11ae9c40041fa30f4a2c`  
**Feature:** `43c87f469d09b97bd345d082e6a916a2299bb351`

## Kết luận điều hành

**SOURCE/ZIP: PASS; DISPOSABLE WINDOWS STAGING: CONDITIONAL GO; LIVE DEPLOYMENT/MAIN MERGE: HOLD.**

Lý do: PR đã sửa lại đóng gói tránh cuốn theo DataDir/khóa nhạy cảm, bootstrap schema và cleanup; chứng cứ mã nguồn, ZIP, một số regression độc lập đều đạt. Nhưng lịch sử Git công khai từng chứa ZIP nhạy cảm, vòng xoay/revoke credential do owner phụ trách chưa đóng; C13 chỉ có kết quả trên runtime FastAPI 0.115.14 do Cursor báo; chưa có bằng chứng Windows/EZVIZ/face/installer trên máy thật.

## 1. Chain-of-custody và tính toàn vẹn

- Uploaded bundle: `MyPC-PR14-956ec4d8d11f-UPLOAD-TO-CHATGPT.zip`.
- Uploaded bundle SHA256 `abcf40fb138f81137b9e75031407a23b375b3e752307eb139254eac38a1ae38a`, CRC PASS, 17 entries.
- Changed ZIP: SHA256 `ddad6d9d7aa2c81f516f42464357c7a1415def392c8ef94f6aa74acdeb3bdf2c`, CRC PASS, 28 files.
- Full ZIP: SHA256 `d7872e52be6c084ecda882ffdba0db61b0e467a51eb2ad99c46a3ccdf82dff5a`, CRC PASS, 349 files.
- Changed 28/28 là tập con có nội dung byte trùng hệt Full.
- Quét đường dẫn nhạy cảm từ tool mới (`sensitive_path_scanner.py`) trên *cả hai ZIP* PASS; không thấy `data/`, `secrets/`, `.sqlite3`, `FIRST_RUN_ADMIN.txt`, `master.key`, `session.secret`, `face_templates.key` theo đường dẫn. Quét đường dẫn không phải quét nội dung thông tin nhạy cảm trong tài liệu nguồn.
- Đối chiếu 9 tệp quan trọng (bootstrap, finalize route/middleware, outbox, migration, main, packaging/scanner, test) bằng Git blob SHA1: **9/9 khớp GitHub** tại HEAD nêu trên.
- `FINAL_HEAD.txt` trong handoff ghi `4f865e8ea95b7738008c19269a14dc63b5f0256f` khác HEAD GitHub `956ec4d8...`; GitHub compare xác nhận **một commit sau 4f865e chỉ thay đổi file FINAL_HEAD.txt**, không thay đổi app code. P2 provenance housekeeping; không nên sửa bằng cách tự nhúng tip SHA trong cùng commit.

## 2. Security-P0 — trạng thái thực tế

**PASS ở gói release mới:** Full/Changed không chứa các đường dẫn dữ liệu nhạy cảm bị phát hiện trước đó; có `tools/package_clean_source_zips.py` dùng danh sách git tracked, loại các nguồn nguy hiểm; scanner có đọc ZIP lồng nhau theo tên entry.

**OWNER ACTION / chưa đóng:** Các ZIP cũ đã xuất hiện trong repository public/lịch sử Git. Đổi/thu hồi credential còn hiệu lực, đánh giá session signing key, master key, và kế hoạch re-wrap face template trước khi xoay khóa. Xóa file ở HEAD **không xóa Git history và bản đã tải về**. Lịch sử rewrite cần owner phê duyệt, bảo vệ bản sao/refs và phối hợp mọi clone trước khi thao tác.

**Giới hạn:** `tools/sensitive_path_scanner.py` kiểm tra đường dẫn và nested ZIP; chưa có content-level credential scanner xác minh tất cả `.md/.py/.json` không chứa giá trị thực. Không được tái phát hành các ZIP cũ đã quarantine.

## 3. Install-P0 — bootstrap schema

- `backend/app/core/schema_bootstrap.py` đã tách rõ: empty DB → ORM create_all + stamp Alembic HEAD `20261103_0012`; versioned DB → migrate; legacy tables without `alembic_version` → fail closed.
- Thử độc lập `test_clean_install_migrates_to_head_and_survives_second_boot` PASS.
- Thử độc lập `test_upgrade_pre_0010_preserves_camera_and_integrity` PASS. **Caveat:** fixture này tạo bảng từ ORM schema hiện tại rồi giả lập version `0008`; chưa thay thế kiểm thử nâng cấp từ *một DataDir cũ thực tế*.
- Thử độc lập `test_unknown_legacy_db_fails_closed_without_auto_stamp` PASS.
- Cổng cài trắng/nâng cấp Windows thực tế chưa có bằng chứng (INSTALLER BLOCKED).

## 4. Cleanup-P1 / transaction

- `queue_promote()` đăng ký `discard_on_rollback` trước `db.flush()`.
- Test `test_failed_outbox_flush_leaves_no_staged_blob_or_lease` PASS độc lập.
- C11, C12, C14, các test SQLite C01-C10 và ACL / retry trọng tâm trong nhóm 28 bài PASS.
- Có SQLite commit-proven outbox, generation và lifecycle fence; không xác định tái phát hiện C11/C12/C14 từ lượt kiểm thử này.

## 5. Compat-P1 — C13 (HTTP 503)

- Source yêu cầu FastAPI `>=0.115.0,<0.116`; Cursor báo đã chạy FastAPI `0.115.14` và C13 PASS, 295 passed toàn bộ trên Python 3.12.3.
- Môi trường audit chạy Python 3.13.5, FastAPI 0.128.2. Từ bản 0.118 FastAPI thay đổi lifecycle của yield dependency, vì vậy kết quả từ bản 0.128 không dùng nghiệm thu C13 trên bản 0.115.x.
- Không thể cài lại 0.115.14 trong môi trường audit vì DNS tới PyPI không khả dụng.
- Một lượt test nhóm C13 trên môi trường không được hỗ trợ bị treo; **không kết luận bản Windows pin đúng cũng bị lỗi**.
- C13 **chưa được xác nhận độc lập**. Ở Windows staging, chụp output `python --version`, `pip show fastapi`, `GET /api/v1/health`, và fault-injection một lần với DataDir clone; phải nhận thực tế HTTP 503 `SECRET_FS_OUTBOX_INCOMPLETE` và sau retry về pending=0.
- Để tái lập chính xác, nên khóa bản phát hành tới **FastAPI==0.115.14** (hiện requirements chỉ khóa khoảng 0.115.x) hoặc phát hành có dependency lock đầy đủ, kiểm tra thực tế installer.

## 6. Test độc lập — không cộng chồng test trùng

- `tests/unit`: **181 passed, 4 skipped, 0 failed**, thời gian 7.21s.
- 31 test trọng tâm được thu thập; loại đúng ba bài phụ thuộc FastAPI hỗ trợ/C13 trên runtime không phù hợp → **28 passed, 3 deselected**, 5.12s. Một số test này có trong `tests/unit`, không cộng 181+28 như test độc lập hoàn toàn.
- `tests/integration` toàn bộ: chưa hoàn tất trước timeout, log có sáu bài đầu tiên báo pass, sau đó dừng; chưa xác định nguyên nhân. Không suy diễn FAIL/PASS cho toàn suite.
- 153 file Python trong Full Source parse AST PASS.
- Cursor handoff tuyên bố `295 passed` trên Python 3.12.3/FastAPI 0.115.14; đây là **kết quả báo cáo**, chưa được tái tạo trọn bộ.

## 7. Gates và quyết định

| Gate | Kết luận |
|---|---|
| ZIP/manifest/code SHA | PASS |
| SEC-02/03 package release mới | PASS (path-level) |
| SEC-04 Git history cleanup / rotate | OWNER ACTION, OPEN |
| INS fresh clean + unknown legacy | PASS độc lập (synthetic) |
| INS upgrade genuine old DataDir | STAGING REQUIRED |
| CLEANUP flush fault | PASS độc lập |
| C01-C12, C14 core scenarios | PASS theo nhóm trọng tâm đã chạy |
| C13 HTTP 503 đúng FastAPI 0.115.14 | CURSOR REPORTED PASS; OWNER WINDOWS RETEST |
| CAMERA_LAB/FACE_PILOT/EXIT/INSTALLER | BLOCKED |

**Cho phép**: triển khai trên máy staging Windows riêng với DataDir rỗng và DataDir sao lưu *dùng một lần*; chỉ mô phỏng lỗi credential trên bản sao.  
**Chưa cho phép**: thay live DataDir, xóa/đổi credential thực, merge PR #14/main, gọi Camera_LAB hoặc Face_Pilot PASS khi chưa có owner evidence.

## 8. Yêu cầu chứng cứ vòng tiếp theo

Không mở phase UI/feature hoặc audit mã nguồn mới nếu không có blocker P0/P1 thực tế. Ưu tiên owner-approved security cleanup song song với Windows staging (xem `WINDOWS_STAGING_GATE_VI.md`). Sau staging cung cấp ZIP chỉ chứa log đã redact, ảnh màn hình đã che thông tin, acceptance matrix và version pins; không đính kèm DataDir, face templates, ảnh nhân viên hoặc khóa.
