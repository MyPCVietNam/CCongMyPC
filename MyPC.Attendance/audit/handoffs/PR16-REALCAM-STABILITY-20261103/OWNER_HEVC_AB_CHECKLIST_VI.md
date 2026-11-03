# Checklist A/B HEVC — owner Windows (read-only / controlled)

**Cloud không có camera thật → physical A/B = BLOCKED tại Cursor.**  
Mỗi lần chỉ đổi **một** biến. Không đổi firmware/mật khẩu/router khi chưa được phép.

## An toàn

- DataDir disposable; không production.
- Không đưa credential vào argv ffmpeg/ffprobe, log, URL công khai.
- Ghi metrics từ app diagnostics (`decode_errors`, `suspected_corrupt_frames`, `reconnect_*`, FPS) — `native_decoder_error_category=UNAVAILABLE` trừ khi có công cụ native riêng.

## Bảng thử

| Run | Biến | Giữ cố định | Đo |
|-----|------|-------------|-----|
| A | H.265 + RTSP/TCP (hiện tại) | độ phân giải, Wi-Fi/RJ45 | 15–30 phút: FPS, corrupt, reconnect, stderr HEVC có/không |
| B | H.265 + UDP (nếu owner duyệt) | còn lại như A | So sánh mất khung / POC warnings |
| C | H.264 + TCP (nếu firmware cho phép) | còn lại | Có hết cu_qp_delta/POC không? LIVE còn ổn? |
| D | RJ45 vs Wi-Fi | codec/transport | |
| E | OpenCV wheel hiện tại vs đối chứng (nếu có) | | YuNet/SFace vẫn OK? |

## Gate ghi nhận

- Functionality / Stability / Recovery / Physical evidence / Safety — xem protocol PR16 §8.
- Không đánh `LIVE_STABILITY_PASS` nếu chỉ chạy vài giây.
- Không đánh `CAMERA_LAB_SIGNED` nếu chưa HMAC verify.
