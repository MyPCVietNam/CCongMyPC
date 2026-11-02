# Khôi phục & chính sách ACL kho bí mật (Windows)

## Hiện tượng

Sau bản Camera/RTSP HF, app có thể báo `PermissionError` / `SECRET_ACCESS_DENIED` với `face_templates.key` rồi `session.secret` dù `icacls` hiện `LONGKYTHUAT-MYP\MyPC:(R,W)`. Nguyên nhân thường gặp:

1. ACL thư mục **không kế thừa `(OI)(CI)`** xuống tệp con.
2. Bản sửa cũ tìm chuỗi SID literal trong output `icacls` → trên máy thật `icacls` in **tên tài khoản** (`DOMAIN\MyPC`) chứ không phải `S-1-…` → báo ACL “hỏng” dù đã đúng → gọi `/inheritance:r` lặp lại.
3. Script PowerShell gán `$home = …` đụng biến tự động `$HOME` (PowerShell 5.1, không phân biệt hoa thường) → `VariableNotWritable`.

## Không làm

- Không xóa / tái tạo `session.secret`, `master.key`, `face_templates.key`, `camera-*.bin`
- Không tạo DataDir mới / không bootstrap admin mới
- Không xóa SQLite, nhân viên, chấm công
- Không cấp quyền cho **Everyone**
- Không chạy repair khi app vẫn LISTEN cổng 8765

## Quy trình (cùng `-DataDir` đang dùng)

1. **Dừng** MyPC Attendance (cổng 8765 không LISTEN).
2. PowerShell **thường** (đúng tài khoản `.\MyPC` / `LONGKYTHUAT-MYP\MyPC`):

```powershell
cd <MyPC.Attendance>
Set-ExecutionPolicy -Scope Process RemoteSigned -Force
.\scripts\windows\Repair-MyPCSecretsAcl.ps1 -CheckOnly
```

Kỳ vọng: `CRITICAL_PRESTART_BACKUP: FOUND_AND_READABLE`, các tệp `READ PASS` hoặc liệt kê `READ DENIED`, `CONTENT_MATCHES_BACKUP` với các khóa đọc được. Script dùng `$attendanceHome` (không còn `$home`).

3. Sửa ACL (PowerShell **Run as administrator** bằng **đúng** tài khoản MyPC):

```powershell
.\scripts\windows\Repair-MyPCSecretsAcl.ps1 -Repair
# gõ chính xác: REPAIR-EXISTING-SECRETS
```

Hoặc Python:

```powershell
.\.venv\Scripts\python.exe scripts\repair_secrets_acl.py `
  --data-dir "$env:LOCALAPPDATA\MyPC\Attendance\data" `
  --repair --yes-i-understand
```

Trước khi đổi ACL, tool sẽ:

- xác nhận app đã dừng
- xác nhận backup khóa quan trọng đọc được
- `icacls /save` ACL thư mục + từng tệp đích
- chỉ cấp quyền cho SID user hiện tại + SYSTEM trên tệp allowlist
- nếu directory policy đã khỏe (SID + `(OI)(CI)` qua `Get-Acl`/`GetNamedSecurityInfo`) → **không** gọi `/inheritance:r` lại

4. Đóng cửa sổ Admin → chạy lại `-CheckOnly` bằng user thường → tất cả `READ PASS`, `DIRECTORY_POLICY: HEALTHY`.
5. Khởi động lại **cùng DataDir**:

```powershell
.\scripts\windows\Start-MyPCAttendance.ps1 -DataDir "$env:LOCALAPPDATA\MyPC\Attendance\data"
```

6. Khởi động **≥3 lần** liên tiếp — không còn `SECRET_ACCESS_DENIED` / `PermissionError`; đăng nhập Admin cũ vẫn được; camera credential giải mã được; nội dung khóa khớp backup.

## Sau khi cập nhật mã nguồn này

- App kiểm tra ACL bằng **Win32 GetNamedSecurityInfo → SID**, không phụ thuộc chuỗi hiển thị `icacls`.
- ACL đã đúng → startup **idempotent** (không mutation).
- Khóa cũ không đọc được → fail-closed `SECRET_ACCESS_DENIED` (không tái tạo).

## Cổng vật lý (owner)

Toàn bộ case ACL-WIN* trong `docs/PR11_SECRET_ACL_WINDOWS_MATRIX.csv` giữ **BLOCKED** cho đến khi owner gửi bằng chứng máy Windows thật (audit `-CheckOnly`, repair, 3 lần restart, hash khớp backup).
