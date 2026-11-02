# Hướng dẫn kiểm camera EZVIZ trên Windows 10/11 (MyPC Attendance)

## Mục tiêu

Chạy ứng dụng **chỉ trên máy Windows nội bộ** (localhost `127.0.0.1:8765`), gắn camera EZVIZ công ty qua LAN, đo khung LIVE thật, rồi mới xem xét mở cổng `CAMERA_LAB` / `FACE_PILOT`.

**Agent Cloud không thể PASS các cổng vật lý.** Nếu chưa có bằng chứng Windows LAN: giữ **BLOCKED**.

## An toàn

- Không đưa mật khẩu RTSP vào tham số dòng lệnh, script Git, log hay ZIP bàn giao.
- Không mở `0.0.0.0`, không tunnel Cloud tới camera.
- Không lưu ảnh khuôn mặt / embedding vào ZIP công khai.
- Cấu hình camera chỉ trong UI đã đăng nhập (kho bí mật OS).

## Bước 1 — Kiểm sẵn sàng (chỉ đọc)

Trong PowerShell 5.1 hoặc 7, tại thư mục `MyPC.Attendance`:

```powershell
.\scripts\windows\Readiness-PR8.ps1 -CameraHost 192.168.x.x -OutputDirectory "$env:ProgramData\MyPC\Attendance\camera-lab"
```

Xem JSON đã lọc. `TCP_REACHABLE` **không** bằng RTSP decode hay CAMERA_LAB PASS.

## Bước 2 — Khởi động local

```powershell
.\scripts\windows\Start-MyPCAttendance.ps1
```

Mở trình duyệt: `http://127.0.0.1:8765` — đăng nhập admin nội bộ.

## Bước 3 — Gắn camera trong UI

1. Tạo/sửa camera (host IPv4 LAN, không hostname công cộng).
2. Lưu username/password RTSP trong UI (không paste vào PowerShell).
3. Gắn nguồn LIVE / mở preview.
4. Xác nhận provenance hiển thị `CAMERA_LIVE` (không phải MOCK/REPLAY).

## Bước 4 — Lab run CAMERA_LAB

Lấy CSRF + cookie phiên từ trình duyệt (DevTools), rồi:

```powershell
.\scripts\windows\Invoke-MyPCLabRun.ps1 -CameraId <id> -Kind CAMERA_LAB `
  -CsrfToken <csrf> -SessionCookie <cookie> -Step start
# Ghi lại run_id và owner_challenge

.\scripts\windows\Invoke-MyPCLabRun.ps1 -CameraId <id> -Kind CAMERA_LAB `
  -CsrfToken <csrf> -SessionCookie <cookie> -Step measure -RunId <run_id>

.\scripts\windows\Invoke-MyPCLabRun.ps1 -CameraId <id> -Kind CAMERA_LAB `
  -CsrfToken <csrf> -SessionCookie <cookie> -Step owner-review `
  -RunId <run_id> -OwnerChallenge <challenge>

.\scripts\windows\Invoke-MyPCLabRun.ps1 -CameraId <id> -Kind CAMERA_LAB `
  -CsrfToken <csrf> -SessionCookie <cookie> -Step promote -RunId <run_id>
```

Sau đó ký phê duyệt `CAMERA_LAB` trong UI với `evidence_id` vừa tạo. Cổng vẫn coi là chưa PASS cho đến khi ký hợp lệ.

## Bước 5 — FACE_PILOT (đồng ý mẫu)

Cần ≥1 case **KNOWN** và ≥1 case **UNKNOWN** do **server** đo trên khung LIVE (không gửi số đếm client). Điều kiện ánh sáng: DAY / DUSK / NIGHT_IR / BACKLIGHT.

Dùng API `.../lab-runs/{run_id}/face-cases` với `truth_label` = `KNOWN:<employee_id>` hoặc `UNKNOWN`, rồi owner-review → promote → ký `FACE_PILOT`.

## Kiểm tra nên làm trên máy công ty

- Ban ngày, chiều tối / hồng ngoại, ngược sáng
- Rút/cắm lại camera, reboot camera, restart dịch vụ, reboot Windows
- Sai mật khẩu / sai path RTSP → lỗi tiếng Việt, **không** lộ secret trong log
- Đăng ký full-frame + quy tắc AM/PM hiện có (08:15–08:45 / 17:00–23:56)
- Windows Defender / user thường — không hạ thấp bảo mật máy

## Cổng vẫn BLOCKED nếu

- Chỉ chạy trên Cloud / MOCK
- Chỉ có health W/H cũ, không lab-run FSM
- Chưa có owner challenge + promote
- Chưa có case FACE_PILOT server-measured
- Chưa có bộ cài `.exe` đã kiểm trên Windows (`INSTALLER`)
