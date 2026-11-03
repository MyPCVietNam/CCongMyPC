# Checklist FACE_PILOT & EXIT_VERIFICATION (BLOCKED)

**Trạng thái Gate 01:** **BLOCKED**.  
Chỉ chạy với người đã đồng ý; không đưa ảnh khuôn mặt vào báo cáo công khai.

## FACE_PILOT

- [ ] Enrollment trên volunteer đã consent (ghi acknowledgements theo quy trình công ty)
- [ ] Nhận diện đúng người / nhầm người / không nhận diện — đo theo tiêu chí nghiệm thu nội bộ v1.5
- [ ] Buổi sáng và buổi chiều theo cửa sổ cấu hình hiện có — **không** tự đổi rule attendance
- [ ] Template lưu encrypted; xoá/revoke enrollment thử trên staging

## EXIT_VERIFICATION

- [ ] Khung giờ / cửa sổ chiều theo config đã ack
- [ ] Quyết định vào/ra khớp policy owner đã duyệt
- [ ] Không silent change business rules trong PR này

## Bằng chứng

- Bảng số liệu (true/false accept rates) **không** kèm ảnh mặt
- Config version / ack timestamp
- Ghi rõ CAMERA_LAB phải PASS trước khi kết luận FACE_PILOT vận hành
