# Owner Windows (BLOCKED until camera ON)
1. Bật Windows LAN + camera vật lý.
2. Sau khi đổi host/RTSP/credential/mock: bắt buộc LIVE rebind + lab FSM mới (NEEDS_REBIND).
3. Tạm tắt camera (enabled=false) không hủy PHYSICAL; bật lại cùng nguồn có thể ký lại nếu revision/pins còn khớp.
4. Không đánh FACE_PILOT / LIVE_STABILITY / INSTALLER / production từ cloud.
