# Owner Windows — P02 face overlay acceptance (BLOCKED until owner runs)

## Deploy candidate without touching signed staging DataDir

1. Giữ nguyên staging HF5 đang ký (`127.0.0.1:18876` + DataDir hiện tại).
2. Checkout freeze commit P02 vào thư mục **mới**.
3. Tạo DataDir staging **mới** + cổng khác (ví dụ `18877`). Copy chỉ cấu hình cần thiết — **không** ghi đè DataDir đã ký.
4. Trỏ models YuNet/SFace đã SHA256-verify (giống staging cũ).
5. Rollback: dừng cổng mới; staging cũ vẫn nguyên.

## Smoke overlay (consented adult tại cửa, nhìn lên, không đội mũ)

1. Bật LIVE; xác nhận decoder LIVE (lane a) — **không** coi đó là AI.
2. Bật checkbox **AI phát hiện khuôn mặt (overlay)** (mặc định tắt).
3. Quan sát khung + ROI arrival; đọc `face_width_px` native từ panel (d) — **không** PASS từ zoom/screenshot.
4. Một người: kỳ vọng OK hoặc FACE_TOO_SMALL/OUTSIDE_ROI có lý do rõ.
5. Hai người trong khung: MULTIPLE_FACES — không ủy quyền chấm công.
6. Tắt AI → MJPEG mượt trở lại.
7. Sửa ROI nháp → Lưu; xác nhận CAMERA_LAB signed vẫn còn (lane e); FACE_PILOT vẫn pending (f).

## Không làm
Không export secrets/DataDir/ảnh NV/embeddings. Không đánh LIVE_STABILITY_PASS / PRODUCTION_READY từ cloud.
