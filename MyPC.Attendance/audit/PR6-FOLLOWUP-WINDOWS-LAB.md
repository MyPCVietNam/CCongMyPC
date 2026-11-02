# PR6 Follow-up — Windows Lab

## Script

`scripts/windows/Test-MyPCCamera.ps1` extended with:

- destination pin / secret-entry / ffprobe / installer honesty steps
- optional local `GET /api/v1/health` probe (TCP/health ≠ CAMERA_LAB PASS)
- Vietnamese owner guidance to configure IPv4 RTSP in-app

## Status

| Item | Status |
|------|--------|
| Script runs on this Linux agent | **NOT_RUN** (PowerShell owner PC) |
| EZVIZ H8 Pro decode W/H/FPS | **BLOCKED** |
| NTFS ACL on session.secret | **BLOCKED** |
| Installer build/uninstall | **BLOCKED** |
| CAMERA_LAB_PASS | **false** |

## Owner one-liner (VI)

Cấu hình RTSP bằng IPv4 LAN trong ứng dụng localhost → xem `/gateway/health` + preview (DECODED_MEASURED) → đo DAY/IR → ký CAMERA_LAB khi đủ bằng chứng; không đánh PASS từ TCP.
