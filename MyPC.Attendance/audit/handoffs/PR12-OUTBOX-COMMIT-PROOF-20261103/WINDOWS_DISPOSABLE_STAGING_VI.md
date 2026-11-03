# Quy trình staging disposable (Windows) — outbox commit-proof

**Không** chạy REPLACE/REMOVE/hard-delete trên DataDir production của owner.

## Chuẩn bị
1. Dừng dịch vụ MyPC Attendance.
2. Sao chép toàn bộ DataDir (file SQLite + `-wal`/`-shm` nếu có + thư mục `secrets/`) sang thư mục tạm chỉ dùng để thử.
3. Triển khai build chứa `feature_commit` trong `FEATURE_COMMIT.txt` (`6503713e683ee0d31a8c7d37a50a636139b47bf4`).
4. Trỏ cấu hình app vào DataDir clone — không trỏ vào DataDir thật.

## Kiểm trên clone
1. **REPLACE** credential → xác nhận mật khẩu mới dùng được; SQLite `secret_generation` tăng; không còn `camera-*.staged-*.bin` orphan.
2. Gây lỗi sau commit (hoặc dừng process giữa commit và promote): khởi động lại hoặc `POST /api/v1/system/secret-fs-outbox/retry` với quyền **SETTINGS_APPLY** + CSRF. Credential live phải khớp DB.
3. Hai phiên admin cùng REPLACE/REMOVE một camera: kết quả live = generation cao nhất đã commit.
4. Configure LIVE rồi lỗi trước commit: không còn decoder gắn khi DB rollback.
5. Hard-delete chỉ camera không còn lịch sử trên clone.

## Diagnostics
- `GET /api/v1/health` — readiness (không đổi).
- `GET /api/v1/system/diagnostics` — chỉ `pending_count` (không path/error).
- Retry outbox: bắt buộc đăng nhập admin có `SETTINGS_APPLY`.

## Cổng vật lý
CAMERA_LAB / FACE_PILOT / EXIT_VERIFICATION / INSTALLER = **BLOCKED**.

## Xác minh ZIP
Chạy `Verify-MyPC-PR12-OutboxZips.ps1 -Commit <GitHub_PR_HEAD>` sau khi push; đối chiếu SHA256SUMS.txt.
