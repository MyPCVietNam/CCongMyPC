# Bước tiếp theo cho chủ sở hữu (Quality Guard v1.0)

**HOLD runtime.** Không chạy Prepare / Start / Stop / synthetic lab trên máy Windows owner.

1. Đọc `INDEPENDENT_REVIEW_V3ADD.md` và `OVERLAY_INTEGRITY.txt`.
2. Xác minh Actions 4 job trên tip: guard-contract, backend-linux, frontend, windows-contract.
3. Audit độc lập COMPLETE HF3 mới (`b79614c3…`) trước khi bất kỳ thao tác runtime nào.
4. Gate vật lý vẫn BLOCKED: USB_WINDOWS_PHYSICAL, USB_STABILITY_30_MIN, USB_CAMERA_LAB_OWNER_SIGN, FACE_PILOT, INSTALLER, PRODUCTION_READY.

Quality Guard đã gắn vào PR #27; không merge main; không force-push.
