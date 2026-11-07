# Ghi chú chủ sở hữu — V3 additional (HOLD)

**Không Start / Stop / Update / Prepare** candidate HF3 trên máy Windows owner cho đến khi audit độc lập COMPLETE mới (`b79614c3…`) xong.

- Cổng chỉ `127.0.0.1:18878`; không đụng 18876/18877, DataDir owner, HMAC, webcam.
- Synthetic lab (`-RunSyntheticLab`) chỉ trên CI cô lập có `MYPC_HF3_SYNTHETIC_LAB_APPROVED=1` — **không** chạy trên máy owner.
- Gate vật lý vẫn BLOCKED: USB_WINDOWS_PHYSICAL, USB_STABILITY_30_MIN, USB_CAMERA_LAB_OWNER_SIGN, FACE_PILOT, INSTALLER, PRODUCTION_READY.

CI code (tip `a0e88ef`): https://github.com/MyPCVietNam/CCongMyPC/actions/runs/42354905763 — 4 job SUCCESS. Đó không phải dấu physical PASS.
