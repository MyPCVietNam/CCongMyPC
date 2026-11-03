# Checklist INSTALLER Windows (BLOCKED)

**Trạng thái Gate 01:** **BLOCKED** — cloud không chạy Windows installer.

- [ ] Cài sạch trên Windows 10/11 lab không có sẵn Python/Node ngoài bundle (nếu installer đóng gói runtime)
- [ ] Service/port/firewall đúng; chạy được sau reboot
- [ ] Nâng cấp từ bản trước (staging) giữ DataDir
- [ ] Gỡ cài — không để lại secret world-readable
- [ ] ACL thư mục `secrets/` đúng owner service
- [ ] Rollback: restore DataDir backup + bản binary trước
- [ ] `pip show fastapi` / health `fastapi_supported` nếu dùng môi trường pip

Nộp: `WINDOWS_INSTALLER_REPORT.md` đã redact — không kèm DataDir.
