# Kế hoạch A/B có kiểm soát — EZVIZ H8 Pro 3K (Windows LAN)

Chỉ đổi **một** biến mỗi lần chạy. Ghi log gián đoạn, khung hỏng, thời gian khôi phục, CPU/RAM, độ phân giải DECODED, FPS.

| # | Biến duy nhất | Giữ cố định | Ghi nhận |
| --- | --- | --- | --- |
| 1 | Codec H.265 (baseline chủ) | TCP, cùng AP/cáp, MAIN | HEVC POC / cu_qp_delta, corrupt count |
| 2 | Codec H.264 | TCP, cùng mạng như #1 | So sánh corrupt / reconnect |
| 3 | Transport TCP | Codec thắng ở #1–2 | Mất khung / reconnect |
| 4 | Transport UDP | Cùng codec như #3 | Mất khung / reconnect |
| 5 | Wi-Fi | Codec+transport ổn định | Latency, interrupt |
| 6 | Ethernet RJ45 | Giống #5 trừ medium | Latency, interrupt |

Mỗi run ≥ ổn định quan sát được (khuyến nghị 30 phút nếu owner cho phép). Không đánh dấu CAMERA_LAB_PASS từ A/B này — cần HMAC + bằng chứng vật lý riêng.

**Không** tắt cảnh báo FFmpeg để “giả sạch”. Khung DEGRADED/corrupt không đưa vào nhận diện.
