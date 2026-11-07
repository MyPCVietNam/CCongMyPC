# Runbook chủ sở hữu — HF3 V4 (HOLD runtime)

**Không** chạy Prepare / Start / Stop / Update / synthetic lab trên máy Windows owner trong giai đoạn này.

1. Đợi audit độc lập COMPLETE V4 (`MYPC-HF3-V4-COMPLETE-AUDIT.zip`) và xác minh SHA256.
2. Chỉ khi audit độc lập GO **và** có phê duyệt tường minh mới được Start trên `127.0.0.1:18878`.
3. Không đụng cổng 18876/18877, DataDir owner, HMAC, webcam, models.
4. Gate vật lý vẫn BLOCKED: USB_WINDOWS_PHYSICAL, USB_STABILITY_30_MIN, USB_CAMERA_LAB_OWNER_SIGN, FACE_PILOT, INSTALLER, PRODUCTION_READY.

Trạng thái hiện tại: **READY_FOR_INDEPENDENT_REAUDIT** — **không** phải OWNER_START_APPROVED.
