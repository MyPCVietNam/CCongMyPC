# MyPC Attendance — Camera thật / Windows Lab (hướng dẫn toán tử)

**Giữ nguyên** `%LOCALAPPDATA%\MyPC\Attendance\data` (SQLite, secrets, nhân viên, chấm công, credential camera).

## Trước khi nâng cấp mã

1. Dừng app (cổng 8765 không LISTEN).
2. Sao lưu toàn bộ thư mục Attendance (kể cả `data\`, `data\secrets\`, `*.sqlite3*`, WAL/SHM).
3. Khôi phục thử lên thư mục **dùng một lần rồi xóa** — xác nhận mở được DB + đọc được secrets trước khi đụng máy thật.

## Khởi động / chẩn đoán (PowerShell 5.1)

```powershell
cd <MyPC.Attendance>
Set-ExecutionPolicy -Scope Process RemoteSigned -Force
.\scripts\windows\Invoke-MyPCDiagnostics.ps1
.\scripts\windows\Start-MyPCAttendance.ps1 -DataDir "$env:LOCALAPPDATA\MyPC\Attendance\data"
```

Script không gán `$HOME`/`$home`, có UTF-8 BOM, không gọi `npm.ps1`.

## Camera / LIVE

1. Giữ camera #1 LIVE đang chạy — không xóa.
2. Dùng **Dry-run trùng lặp** trên trang Camera để xem nhóm host/path trùng; chỉ archive/xóa cứng bản sao **không còn lịch sử**.
3. Xem trước mặc định: **LIVE MJPEG** (mượt). **SNAPSHOT** = ảnh tĩnh có nhãn, không phải full-motion.
4. Trạng thái UI: CONNECTING / LIVE / DEGRADED / RECONNECTING / STALE / OFFLINE / MOCK — badge xanh LIVE chỉ khi decoder OK + integrity.
5. So sánh TCP/UDP hoặc H.265/H.264 hoặc Wi-Fi/RJ45: **chỉ một biến mỗi lần**, tuần tự, ghi log.

## Windows Lab

Thứ tự bắt buộc (UI khóa bước sai):

1. Chọn đúng một camera vật lý → Bắt đầu lab run  
2. Đo LIVE (khung phân biệt)  
3. Lấy challenge (chỉ khi `LIVE_MEASURED`)  
4. Owner review (một toán tử)  
5. Promote PHYSICAL  

`PHYSICAL_VERIFIED` ≠ `camera_lab_pass`. FACE_PILOT hiện **N/A** khi chỉ chạy CAMERA_LAB. Cổng CAMERA_LAB / FACE_PILOT / EXIT / INSTALLER vẫn **BLOCKED** đến khi có bằng chứng vật lý đủ.

## Không làm

- Không tái tạo `session.secret` / `master.key` / `face_templates.key` / `camera-*.bin`
- Không dùng MOCK để vượt CAMERA_LAB
- Không merge main từ nhánh này nếu chưa được chủ sở hữu chấp nhận
