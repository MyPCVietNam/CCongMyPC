# Staging disposable (Windows) — PR13 release safety

**Không** chạy CREATE/REPLACE/REMOVE/hard-delete credential trên DataDir production.
**Không** dùng ZIP FULL cũ đã quarantine (có `data/` / `secrets/`).

## Chuẩn bị
1. Dừng dịch vụ. Sao chép toàn bộ DataDir (SQLite + `-wal`/`-shm` + `secrets/` + master key + face templates) sang thư mục tạm.
2. Xác minh runtime: Python 3.12.x và `fastapi>=0.115,<0.116` (`pip show fastapi`). `/api/v1/health` phải báo `fastapi_supported=true`.
3. Triển khai `feature_commit` trong `FEATURE_COMMIT.txt`. Trỏ app vào clone.
4. Khởi động trên clone:
   - DataDir trống mới: kỳ vọng `alembic_ok=true`, Alembic HEAD `20261103_0012`.
   - DataDir cũ đã có `alembic_version`: upgrade tới HEAD; camera/secrets/history giữ nguyên; `PRAGMA integrity_check = ok`.
   - DB có bảng app nhưng **không** có `alembic_version`: app phải `alembic_ok=false` (không auto-stamp).

## Kiểm trên clone
1. REPLACE credential + lỗi đĩa khi promote → HTTP **503** `SECRET_FS_OUTBOX_INCOMPLETE`; outbox SQLite còn pending; retry `POST /api/v1/system/secret-fs-outbox/retry` (SETTINGS_APPLY + CSRF) hoặc restart.
2. C11–C14 vẫn đúng (không scrub staged in-flight; metadata PATCH giữ; lifecycle fence).
3. `pending_count=0` trước khi kết thúc phiên staging.

## Rollback
1. Dừng app. Khôi phục DataDir từ bản sao đã verify.
2. Không xóa thủ công `camera-*.bin` khi SQLite còn `secret_ref`.
3. Không regenerate `face_templates.key` nếu chưa có kế hoạch re-wrap template.

## Cổng vật lý
CAMERA_LAB / FACE_PILOT / EXIT_VERIFICATION / INSTALLER = **BLOCKED**.

## SECURITY owner
Lịch sử Git công khai vẫn có thể chứa blob ZIP cũ — cần owner-approved `git filter-repo`/BFG + rotate credential. Xóa tip commit **không đủ**.
