# MyPC Attendance — Các bước nghiệm thu Windows staging sau PR #14

**Chỉ dùng máy/VM staging, DataDir mới hoặc bản sao dùng một lần. Không dùng DataDir production.**

## Chuẩn bị có kiểm soát

1. Xác minh PR #14 HEAD `956ec4d8d11fc4e6eecc755d2fed8ae7943c4ec7`, feature `43c87f469d09b97bd345d082e6a916a2299bb351`, checksum nguồn trong `AUDIT_REPORT_VI.md`.
2. Trên Windows staging, xác nhận Python 3.12.x và `fastapi==0.115.14` (hoặc đúng lock đã kiểm thử), `pip check`, quyền chạy dịch vụ. Chụp log phiên bản vào evidence.
3. Đảm bảo app staging chạy port/service riêng, không kết nối DataDir production. Để sao lưu SQLite WAL an toàn, **dừng dịch vụ trước khi sao chép**, lấy đầy đủ SQLite, `-wal`, `-shm`, `secrets/`, face templates, các file key và ACL theo quy trình của owner. Không đưa bản sao này lên GitHub hoặc gửi ChatGPT.
4. Tạo **hai môi trường độc lập**: (A) DataDir rỗng, (B) clone backup DataDir thực dùng thử. Chỉ hoạt động với dữ liệu/mật khẩu giả trong phần test phá hủy.

## Gates cài đặt

- **NEW INSTALL:** database rỗng; app khởi động thành công; `GET /api/v1/health`: `alembic_ok=true`, `fastapi_supported=true`; SQL `SELECT version_num FROM alembic_version` phải là `20261103_0012`.
- **SECOND BOOT:** khởi động lại bình thường; không duplicate table/column; SQLite `PRAGMA integrity_check` = `ok`.
- **UPGRADE:** clone snapshot DB có version cũ; ghi nhận số camera/employee/attendance/template trước và sau, credential đọc được; không làm mất ACL, khóa, template; migration tới 0012. Với DB có bảng nhưng không có alembic_version, phải từ chối migration chứ không auto-stamp.
- **C13 HTTP:** trên staging clone có credential giả, mô phỏng promote lỗi sau SQLite commit; nhận HTTP **503** và `detail.code=SECRET_FS_OUTBOX_INCOMPLETE` trên wire; committed intent còn trong SQLite. Sau retry bằng admin có `SETTINGS_APPLY`+CSRF hoặc restart, pending_count=0 và credential LIVE khớp trạng thái DB.
- **C11/C12/C14:** xác nhận staging không scrub in-flight; cập nhật tên/IP/model đồng thời REPLACE không mất metadata; recreate camera ID không làm replay DELETE cũ xóa credential mới.

## Gates vật lý riêng biệt

- CAMERA_LAB: kiểm tra EZVIZ RTSP HEVC có thể giải mã thật, trạng thái decoder/decoded frame ổn định, log không nhầm MOCK là LIVE, ghi lại buổi đo kéo dài theo protocol.
- FACE_PILOT: test trên người đã đồng ý, đo nhầm người/không nhận diện theo tiêu chí nghiệm thu, không đưa ảnh khuôn mặt vào báo cáo công khai.
- EXIT_VERIFICATION: kiểm chứng hình ảnh cuối và khung thời gian chấm công v1.5 đúng quyết định owner, không tự đổi quy tắc.
- INSTALLER: cài/gỡ/nâng cấp/rollback Windows, port/firewall/service/permission/ACL, không phụ thuộc Python/Node không có trong bộ cài.

## Lưu bằng chứng an toàn

Tạo một ZIP chỉ gồm: `RUNTIME_VERSIONS.txt`, `INSTALL_SQLITE_GATE.txt`, `C13_WIRE_RESPONSE_REDACTED.txt`, `STAGING_SMOKE_MATRIX.md`, `WINDOWS_INSTALLER_REPORT.md`, các log đã loại token/IP/mật khẩu/biometric. Không gửi `data/`, `secrets/`, database, ảnh nhân viên, private key hay mật khẩu.

**SECURITY OWNER:** Cần đánh giá/thu hồi credential công bố và owner-approved Git history cleanup trước khi thông báo release công khai hoặc vận hành production.
