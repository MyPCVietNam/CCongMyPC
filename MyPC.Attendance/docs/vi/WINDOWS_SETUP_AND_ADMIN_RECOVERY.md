# Hướng dẫn Windows & khôi phục quản trị (PR10-HF)

## Cài đặt sạch

1. Cài Python 3.12, Node.js LTS, Git (từ nhà cung cấp chính thức).
2. Trong thư mục `MyPC.Attendance`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
```

3. Chọn **một** thư mục dữ liệu rõ ràng (không gộp nhiều hồ sơ):

```powershell
.\scripts\windows\Start-MyPCAttendance.ps1 -DataDir "$env:ProgramData\MyPC\Attendance\data"
```

4. Mở `http://127.0.0.1:8765` — đăng nhập bằng mật khẩu trong `FIRST_RUN_ADMIN.txt` của **đúng** thư mục dữ liệu đang chạy.
5. Màn hình **Đổi mật khẩu bắt buộc** xuất hiện trước dashboard. Đổi xong phải đăng nhập lại.

## Nếu bị 401 khi đổi mật khẩu

- Nghĩa là **mật khẩu hiện tại bị từ chối** — mật khẩu mới **chưa** được lưu.
- Kiểm tra bạn đang dùng đúng hồ sơ (`ProgramData` / `LocalAppData` / `MYPC_DATA_DIR`).
- Chạy đọc-only: `python scripts\inspect_data_profiles.py` (không in mật khẩu).

## Khôi phục offline (chỉ chủ máy)

1. **Dừng** ứng dụng hoàn toàn.
2. Sao lưu thủ công nếu cần, rồi:

```powershell
.\.venv\Scripts\python.exe scripts\offline_admin_recovery.py --data-dir "$env:ProgramData\MyPC\Attendance\data" --yes-i-understand --reason "mat_mat_khau"
```

3. Gõ đúng cụm `RECOVER-ADMIN-PASSWORD`, nhập mật khẩu mới (không dán vào tham số dòng lệnh).
4. Khởi động lại app → đổi mật khẩu bắt buộc lần nữa trong trình duyệt.
5. Nhân viên / chấm công / khuôn mặt **không** bị xóa.

## Cổng vật lý

`CAMERA_LAB`, `FACE_PILOT`, `EXIT_VERIFICATION`, `INSTALLER` vẫn **BLOCKED** đến khi có bằng chứng phần cứng thật trên máy Windows của bạn. TCP camera mở cổng 554 **không** đủ để PASS.
