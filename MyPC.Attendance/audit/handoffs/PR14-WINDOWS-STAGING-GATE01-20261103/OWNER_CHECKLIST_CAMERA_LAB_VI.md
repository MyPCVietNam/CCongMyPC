# Checklist CAMERA_LAB — EZVIZ thực tế (BLOCKED cho đến khi owner chạy)

**Trạng thái Gate 01:** **BLOCKED** (không có camera/lab trong cloud agent).  
Không đánh dấu PASS từ kết quả MOCK.

## Điều kiện tiên quyết

- [ ] Windows staging Gate install/C13 đã PASS trên máy sẽ gắn camera
- [ ] DataDir disposable; credential camera lab (không dùng mật khẩu production nếu tránh được)
- [ ] EZVIZ H8 (hoặc model đã khai báo) trên mạng lab; RTSP reachable từ máy staging
- [ ] Ghi firmware / model trên phiếu nghiệm thu

## RTSP / HEVC / decoder

- [ ] Cấu hình host/RTSP đúng; không SSRF (host nội bộ lab)
- [ ] Provenance badge server = `CAMERA_LIVE` chỉ khi decoder sẵn sàng — không nhầm MOCK thành LIVE
- [ ] `decoder_status=OK`, có frame kích thước/fps ổn định trong ≥ 15–30 phút
- [ ] Log không spam reconnect; ghi số lần drop/reconnect
- [ ] HEVC/H.265: xác nhận OpenCV/ffmpeg stack decode được trên máy này (đúng wheel đã pin)

## Ổn định

- [ ] Chạy liên tục theo protocol lab (ví dụ 1–2 giờ) — ghi biên bản thời gian
- [ ] Restart app giữa chừng — camera bind lại được
- [ ] Mất mạng giả lập ngắn — recover hoặc fail rõ ràng (không treo im)

## Bằng chứng được phép nộp

- Log đã redact (không password RTSP, không IP nếu policy yêu cầu che)
- Screenshot UI badge MOCK/LIVE (không khuôn mặt người)
- Bảng đo fps/resolution/reconnect

**Không** nộp: ảnh người, DataDir, secrets, video có mặt.
