# Hướng dẫn chủ sở hữu (chỉ đọc) — HF3 V4.2

## Trạng thái

- Cổng: **READY_FOR_INDEPENDENT_REAUDIT**
- **CHƯA** được phê duyệt Start/Prepare/Update/Stop trên máy chủ Windows thật.
- Các cổng vật lý / camera / soak 30 phút / installer / production: **BLOCKED**.

## Cấm tuyệt đối cho đến khi có phê duyệt độc lập

1. Không chạy `-Mode Prepare|Start|Update|Stop` trên ứng viên HF3 (`127.0.0.1:18878`).
2. Không chạm cổng **18876 / 18877**, DataDir sản xuất, secrets, HMAC, ảnh khuôn mặt, model pin.
3. Không “làm sạch” bằng cách xóa `src`, `uvicorn.pid`, hoặc `uvicorn.launch.json` khi Prepare từ chối.

## Khi nào được chạy lại (sau reaudit + ký xác nhận)

Chỉ khi ChatGPT/kiểm toán độc lập xác nhận COMPLETE ZIP và chủ sở hữu ký duyệt bằng văn bản.

Chuẩn bị an toàn (tóm tắt):

1. Sao lưu thư mục ứng viên hiện có (nếu có).
2. Chạy `Diagnose` (read-only) trước.
3. `Prepare` chỉ khi thư mục **chưa** có `src` và cổng 18878 trống (đã chứng minh).
4. Nếu `src` đã tồn tại → dùng `Update`, không dùng Prepare phá hủy.

## Exit codes quan trọng (Prepare)

| Mã | Ý nghĩa |
|----|---------|
| `EXIT_PREPARE_EXISTING_SOURCE` | Đã có `src` hoặc launch meta — giữ nguyên, chuyển Update/Diagnose |
| `EXIT_PREPARE_PROCESS_UNKNOWN` | Listener/TCP/CIM/`uvicorn.pid` không an toàn |
| `EXIT_PREPARE_INPUT_INVALID` | ZIP/SHA/models/root không hợp lệ |

## Liên hệ gói

Xem `README.md`, `GATE_MATRIX.txt`, `SHA256SUMS-COMPLETE.txt` (sidecar ngoài COMPLETE).
