# Vấn đề còn mở và hướng xử lý

## P0 / Owner — chưa đóng

1. **Credential / key exposure lịch sử**  
   ZIP FULL công khai từng chứa `data/`, `secrets/master.key`, `session.secret`, `face_templates.key`, `FIRST_RUN_ADMIN.txt`, SQLite.  
   **Hướng xử lý:** Owner đánh giá từng artifact (dev vs thật) → revoke/rotate credential còn hiệu lực; kế hoạch re-wrap face templates trước khi xoay `face_templates.key`. Agent **không** tự rotate.

2. **Git history vẫn chứa blob ZIP cũ**  
   Xóa ở tip **không đủ**.  
   **Hướng xử lý:** Owner-approved `git filter-repo` / BFG + bảo vệ refs/clone (xem `GIT_HISTORY_REMEDIATION_PROPOSAL_VI.md`). Agent **không** rewrite.

## P1 — staging

3. **C13 trên Windows service thật**  
   Cloud đã PASS với FastAPI 0.115.14 + TestClient. Independent audit môi trường 0.128 không dùng để nghiệm thu.  
   **Hướng xử lý:** Owner chạy mục C13 trong `OWNER_CHECKLIST_INSTALL_UPGRADE_VI.md` trên VM staging; chụp HTTP status + `detail.code` đã redact.

4. **Upgrade từ DataDir cũ thật**  
   Cloud chỉ có fixture synthetic.  
   **Hướng xử lý:** Clone disposable sau khi dừng dịch vụ; ghi số liệu trước/sau; drill restore từ backup nếu fail.

## P2 — provenance

5. **`FINAL_HEAD.txt` lệch tip**  
   File trong handoff PR13 ghi `4f865e8…`; tip GitHub `956ec4d…` chỉ thêm pin FINAL_HEAD.  
   **Hướng xử lý:** Lấy tip từ GitHub PR; không cần sửa app.

6. **Nên khóa `fastapi==0.115.14`** (audit gợi ý)  
   Hiện `>=0.115,<0.116`.  
   **Hướng xử lý:** Owner quyết định lock file / pin installer trước phát hành; không chặn Gate 01.

## Không mở vòng audit mã nguồn mới

Không UX/feature/attendance-rule. Sau Gate 01 Windows PASS (owner), chuyển **CAMERA_LAB** rồi **FACE_PILOT** theo checklist vật lý — vẫn BLOCKED cho đến có bằng chứng owner.
