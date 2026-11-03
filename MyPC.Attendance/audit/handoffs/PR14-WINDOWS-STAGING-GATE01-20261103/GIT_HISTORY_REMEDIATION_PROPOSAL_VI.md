# Đề xuất xử lý lịch sử Git (chưa thực hiện)

## Vì sao xóa tip không đủ

Blob ZIP nhạy cảm vẫn reachable qua commit cũ, fork, mirror, và bản đã tải. Xóa file ở HEAD chỉ ngăn phát tán *mới* từ tip hiện tại.

## Đề xuất (cần owner phê duyệt trước khi chạy)

1. **Inventory:** Liệt kê mọi commit/tag chứa `*-FULL-*.zip` có `data/` hoặc `secrets/` (dùng `git log --all --full-history -- '**/*FULL*.zip'` trên máy owner).
2. **Backup:** Mirror clone `--mirror` lưu offline trước mọi rewrite.
3. **Rewrite:** `git filter-repo` (ưu tiên) hoặc BFG để purge các path:
   - `MyPC.Attendance/data/**`
   - handoff `*FULL*PR12-OUTBOX*.zip`, `*FULL*PR13-C11C14*.zip`
   - mọi `FIRST_RUN_ADMIN.txt`, `**/secrets/**` nếu từng track
4. **Force-push có kiểm soát:** Thông báo mọi collaborator; xoá remote backup refs; rotate credentials **trước hoặc ngay sau** rewrite (history rewrite không thu hồi secret đã lộ).
5. **Verify:** Clone mới sạch; `sensitive_path_scanner` trên mọi tag release còn public.

## Agent / Cursor sẽ không làm

- Không `filter-repo` / BFG / force-push.
- Không đổi credential production.
- Không merge main.

## Trạng thái Gate 01

**OWNER ACTION OPEN** — đề xuất sẵn; chờ phê duyệt vận hành.
