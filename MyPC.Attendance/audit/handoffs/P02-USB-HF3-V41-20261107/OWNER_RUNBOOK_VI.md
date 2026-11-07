# Runbook chủ sở hữu — HF3 V4.1 (HOLD runtime)

**Không** chạy Prepare / Start / Stop / Update / synthetic lab trên máy Windows owner trong giai đoạn này.

1. Tải `MYPC-HF3-V41-COMPLETE-AUDIT.zip` từ raw URL bất biến trong `README.md` / `REMOTE_VERIFY.txt`.
2. Đối chiếu SHA256 COMPLETE + 3 ZIP lồng nhau với `SHA256SUMS-COMPLETE.txt`.
3. Gửi COMPLETE cho audit độc lập. Chỉ khi audit GO **và** có phê duyệt tường minh mới được Start trên `127.0.0.1:18878`.
4. Không đụng cổng 18876/18877, DataDir owner, HMAC, webcam, models.
5. Gate vật lý vẫn BLOCKED: USB_WINDOWS_PHYSICAL, USB_STABILITY_30_MIN, USB_CAMERA_LAB_OWNER_SIGN, FACE_PILOT, INSTALLER, PRODUCTION_READY.

Trạng thái: **READY_FOR_INDEPENDENT_REAUDIT** — **không** phải OWNER_START_APPROVED.
