# Staging disposable (Windows) — PR13 C11–C14

**Không** chạy CREATE/REPLACE/REMOVE/hard-delete credential trên DataDir production.

## Chuẩn bị
1. Dừng dịch vụ. Sao chép toàn bộ DataDir (SQLite + `-wal`/`-shm` + `secrets/` + master key + face templates) sang thư mục tạm.
2. Triển khai build `feature_commit` `c2c7ba72e97a176789d30bb4b94171e618c38720`. Trỏ app vào clone.
3. Chạy Alembic tới `20261103_0012` (thêm `lifecycle_id`).

## Kiểm trên clone
1. REPLACE + sửa name/host cùng PATCH — cả metadata và mật khẩu mới phải lưu.
2. Gây lỗi đĩa khi promote — API phải trả **HTTP 503** `SECRET_FS_OUTBOX_INCOMPLETE`; retry với SETTINGS_APPLY hoặc restart.
3. Trong lúc REPLACE đang mở (chưa commit), **không** gọi retry admin trên cùng DataDir nếu nghi ngờ bản cũ; bản này không còn xóa staged in-flight.
4. Hard-delete camera rồi tạo mới (SQLite có thể tái sử dụng id) — secret camera mới không bị DELETE cũ xóa.

## Rollback / recovery
1. Dừng app. Khôi phục DataDir từ bản sao đã verify (SQLite+`secrets/`).
2. Nếu outbox `pending`: `POST /api/v1/system/secret-fs-outbox/retry` (SETTINGS_APPLY + CSRF) trên **clone**, hoặc khởi động lại dịch vụ.
3. Không xóa thủ công `camera-*.bin` khi SQLite còn `secret_ref`.

## Cổng vật lý
CAMERA_LAB / FACE_PILOT / EXIT_VERIFICATION / INSTALLER = **BLOCKED**.
