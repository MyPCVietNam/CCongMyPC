# Acceptance — staged ACL hotfix

| ID | Gate | Result |
|----|------|--------|
| ACL-01 | Allowlist accepts `camera-N.staged-<32hex>.bin` | PASS (unit) |
| ACL-02 | Rejects invalid staged/live names | PASS (unit) |
| ACL-03 | Windows-sim `apply_new_secret_file_acl` live+staged | PASS (unit) |
| ACL-04 | Scrub blob when ACL apply fails | PASS (unit) |
| ACL-05 | Full suite regression | PASS 301 |
| WIN-01 | Owner create LIVE camera on Windows staging | OWNER |
| CAM-LAB | RTSP/HEVC physical | **BLOCKED** |
