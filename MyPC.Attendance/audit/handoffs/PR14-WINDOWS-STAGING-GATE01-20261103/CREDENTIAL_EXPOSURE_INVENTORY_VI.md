# Danh mục phơi bày credential (đường dẫn — không có giá trị bí mật)

**Nguồn:** Quarantine inventories + independent audit PR #13/#14.  
**Agent không đọc, không in, không rotate giá trị thật.**

## Gói đã quarantine (public history từng chứa)

| Archive (tên) | Sensitive path count | Ví dụ đường dẫn (names only) |
|---------------|---------------------|------------------------------|
| `MyPC.Attendance-FULL-PR13-C11C14-c2c7ba72e97a.zip` | 23 | `…/data/*.sqlite3`, `…/data/secrets/master.key`, `session.secret`, `face_templates.key`, `FIRST_RUN_ADMIN.txt`, `cloud-dev2/3/…` |
| `MyPC.Attendance-FULL-PR12-OUTBOX-6503713e683e.zip` | 22 | tương tự |

Chi tiết: `MyPC.Attendance/audit/QUARANTINE_PUBLIC_ARCHIVES/*.QUARANTINED.txt`

## Hạng mục owner cần đánh giá thu hồi / luân chuyển

| Hạng mục | Rủi ro | Gợi ý xử lý (owner) |
|----------|--------|---------------------|
| `FIRST_RUN_ADMIN.txt` bootstrap password | Đăng nhập admin nếu còn đúng production | Đổi mật khẩu admin; vô hiệu bản ghi cũ; không commit lại |
| `session.secret` | Giả mạo session cookie | Rotate session secret → mọi session cũ hết hạn |
| `master.key` | Giải mã secret store camera | Rotate + re-encrypt camera secrets từ nguồn tin cậy / nhập lại trên staging rồi prod có kiểm soát |
| `face_templates.key` | Template sinh trắc học | **Không** xoay mù; lập kế hoạch re-wrap/migrate templates |
| `*.sqlite3` trong ZIP | Schema + metadata + có thể PII | Coi như đã lộ metadata; không tái phát hành |
| Camera passwords trong secret blobs | Truy cập RTSP/ONVIF | Đổi mật khẩu trên camera EZVIZ + cập nhật app sau rotate key |

## Gói release mới (PR14)

CHANGED/FULL `PR13-RELSAFE-43c87f469d09` — scanner path **PASS** (không có các đường dẫn trên). Vẫn không chứng minh nội dung `.md/.py` không chứa secret; không đính kèm DataDir vào evidence công khai.
