# Hướng dẫn nâng cấp Windows (staging) — PR #12 P0 transactional integrity

**Không** áp dụng hard-delete / đổi credential camera trên DataDir production cho đến khi đã kiểm trên bản sao dùng một lần (disposable).

## 1. Sao lưu DataDir đã dừng hoàn toàn

1. Dừng dịch vụ MyPC Attendance.
2. Sao toàn bộ DataDir gồm SQLite (`.db`), file `-wal`/`-shm` nếu có, thư mục `secrets/`, cấu hình.
3. Xác minh bản sao khôi phục được trên thư mục tạm.

## 2. Staging trên bản sao disposable

1. Triển khai build nhánh PR #12 (tip GitHub hiện tại) trỏ **DataDir clone**.
2. Đăng nhập admin; xác nhận nhân viên / chấm công / camera còn nguyên.
3. Thử **đổi credential** camera trên clone: hủy giữa chừng (kill process) — credential cũ phải còn.
4. Thử hard-delete camera **không** còn lịch sử trên clone; camera có lịch sử phải bị chặn / dùng Lưu trữ.
5. Không đánh dấu CAMERA_LAB / FACE_PILOT / EXIT / INSTALLER = PASS nếu chưa có bằng chứng LAN owner.

## 3. Nâng cấp production (chỉ sau khi staging OK)

1. Dừng dịch vụ; backup DataDir lần nữa.
2. Triển khai cùng commit đã nghiệm thu staging; giữ nguyên DataDir.
3. Khởi động ×3; đăng nhập; kiểm Camera LIVE / Kết nối lại.
4. Windows Lab wizard: không dán cookie/CSRF/challenge vào PowerShell.

## 4. Cổng vật lý

| Cổng | Trạng thái |
| --- | --- |
| CAMERA_LAB | BLOCKED đến khi có bằng chứng owner |
| FACE_PILOT | BLOCKED |
| EXIT_VERIFICATION | BLOCKED |
| INSTALLER | BLOCKED |

Quy tắc v1.5 chiều `[17:00, 23:56)`, ảnh ưu tiên 17:55–18:00, mốc 18:00 — **không** đổi im lặng.

## 5. A/B HEVC

Chỉ đổi một biến mỗi lần (H.265↔H.264, TCP↔UDP, Wi-Fi↔RJ45). Heuristic `frame_looks_corrupt` không phải chứng minh bitstream HEVC.
