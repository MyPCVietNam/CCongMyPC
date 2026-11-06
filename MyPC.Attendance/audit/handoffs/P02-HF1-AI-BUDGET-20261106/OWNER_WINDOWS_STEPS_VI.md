# Owner Windows — P02-HF1 (BLOCKED physical)

## Không đụng staging HF5 đã ký (cổng 18876)

1. Giữ nguyên DataDir + cổng 18876 đã `signed_camera_lab`.
2. Deploy **ứng viên P02-HF1** vào thư mục/port/DataDir **riêng** (vd. 18877).
3. Xác nhận YuNet/SFace REAL; bật AI overlay; 1 và 2 trình duyệt — quan sát CPU không nhân theo viewer; box khớp chuyển động.
4. ROI: chỉ chỉnh arrival; xác nhận CAMERA_LAB signed còn sau F5.
5. **Không** đánh LIVE_STABILITY_PASS / FACE_PILOT từ cloud.

## Promote (sau audit ChatGPT + smoke riêng)

1. Offline backup DataDir staging đã ký.
2. Thay **chỉ mã nguồn** (giữ DataDir/models/approvals).
3. Restart; verify signed CAMERA_LAB; rollback = restore binary/code cũ + DataDir backup nếu cần.
4. Không xoay `config_revision`/credential trừ khi chủ đích.
