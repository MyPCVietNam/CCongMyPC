# Owner Windows commissioning (PR16-HF5) — BLOCKED in cloud

**Trạng thái:** CODE_FIX có thể PASS; cổng vật lý (camera / PowerShell / soak) **BLOCKED** cho đến khi owner bật thiết bị. Cursor **không** chạy cổng vật lý và **không** đánh PASS cho LIVE_STABILITY / CAMERA_LAB_OWNER_SIGN / FACE_PILOT / INSTALLER / PRODUCTION.

## Nguyên tắc an toàn (bắt buộc)

1. Chỉ dùng **DataDir staging dùng một lần** + **cổng HTTP tách** (ví dụ `18080`). **Không** trỏ staging vào production DataDir.
2. **Không** xuất: mật khẩu camera, cookie, SQLite production, embeddings, ảnh nhân viên, `master.key` / `session.secret` / `face_templates.key`.
3. Không đổi mật khẩu camera vật lý chỉ để “thử gate” — dùng bản ghi camera synthetic/disposable trên staging.
4. Log chỉ metrics đã sanitize (FPS, frame age, WxH, revision, profile, reconnect count). Không log RTSP userinfo.
5. Sau mỗi thay đổi nguồn vật chất (host / RTSP / credential / mock): kỳ vọng `NEEDS_REBIND` + lab FSM mới; HMAC cũ **không** được tái ủy quyền.

## Chuẩn bị staging (owner)

1. Confirm HF5 review CODE_FIX_PASS + SHA packaging freeze trước khi bật camera.
2. Clone/checkout đúng commit freeze (không dùng tip docs-only nếu khác freeze).
3. Tạo thư mục DataDir mới trống; đặt `MYPC_DATA_DIR` / cấu hình tương đương trỏ vào đó.
4. Chạy backend staging trên cổng riêng; xác nhận production vẫn dừng hoặc cổng khác.
5. Script đọc-only: `tools/owner_windows_safe_evidence.ps1` (health + metrics; không đụng secrets).

## Smoke checks (khi camera ON)

| # | Check | PASS nếu | Không PASS khi |
|---|--------|----------|----------------|
| 1 | `GET /health` + gateway health | 200; revision/profile hiện diện | Secrets trong log |
| 2 | LIVE decode vs RTSP handshake | Phân biệt `HANDSHAKE_ONLY` vs `LIVE_DECODED`; frame age/FPS hợp lệ | Coi handshake là LIVE |
| 3 | Restart process | Bind/runtime phục hồi sạch trên staging | Phục hồi từ production DataDir |
| 4 | Reconnect | Reconnect count tăng có kiểm soát; không leak credential | Crash loop / secret trong stderr |
| 5 | Soak 15–30 phút (tuỳ chọn 60–120) | Metrics ổn định; không fabricated frames | Đánh PASS từ cloud |
| 6 | HEVC A/B có kiểm soát | Owner đồng ý; ghi RCA native vs fallback | Giả định FFmpeg native |
| 7 | Credentials inventory (staging) | Chỉ liệt kê ref/hint đã redact | Export password / blob |
| 8 | HMAC sau PHYSICAL_VERIFIED thật | `signed_camera_lab` verify trên revision/binding hiện tại | Dùng evidence mock / unsigned |
| 9 | FACE_PILOT | **Cổng tương lai riêng** — không mở trong HF5 commissioning | Gộp với CAMERA_LAB |

## Credential / trust regression (staging only)

- `credential_action=keep` + mật khẩu mới, hoặc đổi username giữ mật khẩu cũ → phải rotate `config_revision`, revoke HMAC/PHYSICAL/lab, stale binding, `NEEDS_REBIND`.
- `enabled=false` rồi `true` với cùng nguồn + pin còn khớp → không buộc re-lab chỉ vì toggle; disabled vẫn đóng operational gate.
- Thay host/path/model/firmware/MOCK → material như HF4.

## Export evidence an toàn

Chỉ: health JSON đã sanitize, ma trận acceptance, SHA freeze, log metrics, checklist owner.  
**Cấm:** DataDir zip, SQLite, secrets dir, ảnh, embeddings, HAR có cookie.

## Gates còn BLOCKED (owner-only)

- `WINDOWS_PHYSICAL_SOAK`
- `CAMERA_LAB_OWNER_SIGN` (ký HMAC trên máy owner)
- `LIVE_STABILITY_PASS`
- `HEVC_NATIVE_RCA`
- `FACE_PILOT`
- `INSTALLER`
- `PRODUCTION_ATTENDANCE`
