# Hướng dẫn toán tử Windows (P02S) — camera EZVIZ LAN

## An toàn

- Không đưa cookie phiên, CSRF hay owner challenge vào tham số PowerShell.
- Không lưu challenge/token vào JSON công khai.
- Không mở camera ra Internet; chỉ `127.0.0.1`.
- Không xuất ảnh khuôn mặt / embedding / mật khẩu RTSP.

## 1. Xác minh nguồn PR #9

```powershell
cd C:\path\to\CCongMyPC\MyPC.Attendance
git rev-parse HEAD
git merge-base --is-ancestor 3bd84dfb4dc779bb2c1709b2bd04bbc8843c7f87 HEAD
.\scripts\windows\Readiness-PR9.ps1 -CameraHost 192.168.x.x -OutputDirectory "$env:ProgramData\MyPC\Attendance\camera-lab"
```

Chỉ ancestry PR #8 là **không đủ**. TCP reachability ≠ decode PASS.

## 2. Khởi động local

```powershell
.\scripts\windows\Start-MyPCAttendance.ps1
```

Mở `http://127.0.0.1:8765` — đăng nhập.

## 3. Windows Lab trong UI

Vào **Windows Lab** (`/lab-windows`):

1. Chọn camera LIVE (không MOCK).
2. Bắt đầu lab run CAMERA_LAB hoặc FACE_PILOT.
3. Đo LIVE — server yêu cầu **khung phân biệt** và **FPS > 0**.
4. Lấy challenge trong trình duyệt (bộ nhớ), xác nhận `ack_vi` (một toán tử).
5. Promote PHYSICAL nếu đủ lớp bằng chứng; vẫn cần ký phê duyệt riêng.
6. FACE_PILOT: chỉ outcome **CORRECT** được tính; WRONG / FALSE_ACCEPT **chặn** duyệt; 1 known + 1 unknown **không đủ**.

Giữ nguyên khung BGR gốc cho chất lượng/nhận diện (không upscale để vượt cổng).

## 4. Cổng vẫn BLOCKED nếu

Chưa có pilot LAN thật / chưa đủ mẫu có giám sát / chưa có bộ cài Windows đã kiểm.
EOF
