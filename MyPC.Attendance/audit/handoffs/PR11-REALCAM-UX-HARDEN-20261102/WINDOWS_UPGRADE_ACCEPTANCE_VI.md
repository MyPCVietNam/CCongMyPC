# Hướng dẫn nâng cấp & nghiệm thu Windows (tiếng Việt)

**Nhánh:** `cursor/pr11-realcam-ux-harden-83a8`  
**Baseline:** `416bc2dcca4c6b117249aca02c5293a8e53ffeae`  
**Giữ nguyên:** DataDir, secrets, DB, lịch sử chấm công, credential camera, quy tắc nghiệp vụ đã duyệt.

## 1. Sao lưu trước khi nâng cấp

1. Dừng dịch vụ MyPC Attendance.
2. Sao chép nguyên thư mục DataDir (SQLite + `secrets/` + cấu hình) sang ổ dự phòng.
3. Ghi lại phiên bản/commit đang chạy.

## 2. Nâng cấp cùng DataDir

1. Triển khai bản build từ nhánh/ZIP delivery này (không merge main trong bước này).
2. Khởi động lại trỏ **cùng** DataDir cũ.
3. Đăng nhập admin; xác nhận nhân viên / chấm công / camera vẫn còn.
4. Trang **Camera**: chọn camera LIVE → xem preview → **Kết nối lại** / **Kiểm tra**.
5. **Cài đặt → Phần quản trị → Windows Lab**: chạy wizard từng bước (không dán cookie/CSRF/challenge vào PowerShell).

## 6 nhóm điều hướng mới

1. Tổng quan  
2. Chấm công (gồm tăng ca, đơn nghỉ/công tác)  
3. Nhân viên (gồm đăng ký khuôn mặt)  
4. Camera  
5. Báo cáo  
6. Cài đặt (Windows Lab & Nhật ký nằm trong phần quản trị)

## 3. Nghiệm thu vật lý (owner)

| Cổng | Điều kiện PASS | Trạng thái mặc định |
| --- | --- | --- |
| CAMERA_LAB | Bằng chứng LAN thật + HMAC | **BLOCKED** |
| FACE_PILOT | Case CORRECT đủ sàn, đồng ý | **BLOCKED** |
| EXIT_VERIFICATION | Bằng chứng owner | **BLOCKED** |
| INSTALLER | Cài/gỡ/rollback Windows | **BLOCKED** |

LIVE decode ổn định ≠ CAMERA_LAB_PASS.  
MOCK ≠ LIVE.  
Khung hỏng/HEVC không được dùng nhận diện.

## 4. A/B camera

Xem `AB_TEST_PLAN_VI.md` — một biến mỗi lần (H.265↔H.264, TCP↔UDP, Wi-Fi↔RJ45).

## 5. Khi có sự cố

- Credential vẫn trên đĩa nếu DB rollback (P0-1).  
- Không xóa cứng camera còn lịch sử — dùng **Lưu trữ**.  
- Khôi phục DataDir từ bản sao lưu bước 1 nếu cần.
