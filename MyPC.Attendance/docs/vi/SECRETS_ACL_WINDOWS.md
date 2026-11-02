# Khôi phục & chính sách ACL kho bí mật (Windows)

## Hiện tượng

Sau bản Camera/RTSP HF, app có thể báo `PermissionError` với `face_templates.key` rồi `session.secret` dù thư mục `secrets` hiện `MyPC:(R,W)`. Nguyên nhân: ACL thư mục **không kế thừa (OI)(CI)** xuống tệp con; sửa một tệp không đủ.

## Không làm

- Không xóa `session.secret` / `master.key` / `face_templates.key` / `camera-*.bin`
- Không tạo DataDir mới / không bootstrap admin mới
- Không xóa SQLite, nhân viên, chấm công

## Quy trình (cùng `-DataDir` đang dùng)

1. **Dừng** MyPC Attendance (cổng 8765 không LISTEN).
2. PowerShell thường:

```powershell
cd <MyPC.Attendance>
Set-ExecutionPolicy -Scope Process RemoteSigned -Force
.\scripts\windows\Repair-MyPCSecretsAcl.ps1 -CheckOnly
```

3. Sửa ACL (PowerShell **Run as administrator** bằng đúng tài khoản MyPC):

```powershell
.\scripts\windows\Repair-MyPCSecretsAcl.ps1 -Repair
# gõ: REPAIR-EXISTING-SECRETS
```

Hoặc:

```powershell
.\.venv\Scripts\python.exe scripts\repair_secrets_acl.py --data-dir "$env:LOCALAPPDATA\MyPC\Attendance\data" --repair --yes-i-understand
```

4. Đóng cửa sổ Admin → `-CheckOnly` bằng user thường → tất cả READ PASS.
5. Khởi động lại:

```powershell
.\scripts\windows\Start-MyPCAttendance.ps1 -DataDir "$env:LOCALAPPDATA\MyPC\Attendance\data"
```

6. Khởi động ≥3 lần liên tiếp — không còn `SECRET_ACCESS_DENIED` / `PermissionError`.

## Sau khi cập nhật mã nguồn này

App đặt ACL thư mục secrets với `(OI)(CI)` cho SID người dùng + SYSTEM, **không** gọi `/inheritance:r` mỗi lần nếu ACL đã đúng. Tệp khóa mới kế thừa quyền. Khóa cũ không đọc được → fail-closed `SECRET_ACCESS_DENIED` (không tái tạo khóa).
