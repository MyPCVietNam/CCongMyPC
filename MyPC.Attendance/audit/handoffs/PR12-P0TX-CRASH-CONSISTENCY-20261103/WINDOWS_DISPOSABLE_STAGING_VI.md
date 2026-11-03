# Quy trình thử staging disposable (Windows) — crash/concurrency credential

**Không** chạy REPLACE/REMOVE/hard-delete trên DataDir production.

## Chuẩn bị
1. Dừng dịch vụ. Sao chép toàn bộ DataDir (SQLite + WAL/SHM + `secrets/`) sang thư mục tạm.
2. Triển khai build chứa `feature_commit` trong `FEATURE_COMMIT.txt`. Trỏ app vào DataDir clone.

## Kiểm tra bắt buộc trên clone
1. **REPLACE credential** → xác nhận đăng nhập/LIVE vẫn dùng mật khẩu mới.
2. Mô phỏng lỗi sau commit: nếu API trả `SECRET_FS_OUTBOX_INCOMPLETE` (503) → gọi `POST /api/v1/system/secret-fs-outbox/retry` (có CSRF) hoặc khởi động lại dịch vụ; kiểm `GET /api/v1/system/diagnostics` → `secret_fs_outbox.pending`.
3. Hai phiên admin cùng REPLACE một camera: kết quả live secret khớp DB (không lệch).
4. Configure LIVE rồi hủy/gây lỗi trước commit: không còn decoder gắn khi DB không lưu.
5. Hard-delete chỉ camera không còn lịch sử trên clone.

## Cổng vật lý
CAMERA_LAB / FACE_PILOT / EXIT_VERIFICATION / INSTALLER = **BLOCKED** đến khi có bằng chứng owner.

## Xác minh ZIP
Dùng `Verify-MyPC-PR12-GitHubZips.ps1` (cập nhật `$commit` = GitHub PR HEAD thực tế sau khi push).
