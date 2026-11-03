# Kiểm trên Windows staging (sau hotfix ACL)

1. Checkout feature commit; Python 3.12.x; FastAPI 0.115.14; DataDir disposable.
2. Tạo camera LIVE (hoặc MOCK+credential_action replace) với username/password lab.
3. Kỳ vọng: không còn lỗi `không áp ACL cho tên không nằm trong allowlist: camera-*.staged-*.bin`.
4. SQLite commit + promote: `camera-<id>.bin` tồn tại; không còn `.staged-` orphan sau commit thành công.
5. `icacls` trên `camera-*.bin` / staged (nếu còn trong flight) — user+(M), SYSTEM+(F); không Everyone.
6. CAMERA_LAB vẫn BLOCKED đến khi có bằng chứng RTSP/HEVC thật.
