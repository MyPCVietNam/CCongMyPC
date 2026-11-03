# Bước owner Windows còn lại (BLOCKED cho đến khi camera ON)

1. Bật máy Windows LAN + camera vật lý; không dùng cloud agent làm thay.
2. Chạy lab FSM: measure → owner challenge/review → promote PHYSICAL trên revision hiện tại.
3. Ký HMAC CAMERA_LAB với tài khoản có `PILOT_APPROVE` (CSRF cookie trình duyệt) — chỉ evidence eligible sau HF3.
4. Không đánh dấu FACE_PILOT / LIVE_STABILITY_PASS / INSTALLER / production từ cloud.
5. Giữ DataDir production nguyên; không xoay key trừ khi owner chủ động.
6. Sau khi có bằng chứng Windows thật, nộp evidence sanitize (không cookie/ảnh/embeddings).
