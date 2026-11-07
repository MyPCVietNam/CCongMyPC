# Báo cáo audit nền tảng — MyPC Attendance Quality Guard v1.0

## Nguồn và giới hạn

- Nguồn source thực tế: COMPLETE ZIP được người dùng gửi tại PID Safety V2 (PR #27), freeze `0ea4264440bf330f005af7447bbd6bdb6cfabb46`, SHA256 COMPLETE `58017ee3f09b5e6f21dd6097c390058ff48616cf83cc8b1932e93a32627a0e6a` và FULL `7bd8b000b43cbd832094582816f3c04a05af7585c934ed940c97623e85a10148`. CRC nested PASS.
- GitHub kiểm tra branch PR #27 source `cursor/p02-usb-hf3-dshow-com-enum-83a8`; base `cursor/p02-usb-hf2-verified-binding-83a8`. `main` chỉ có LICENSE khi kiểm tra. Ref HEAD có thể tiếp tục di chuyển sau freeze. Tại lượt kiểm tra gần nhất, tip đã tiến tới `ab1161dd87f0f363ea3974cf68c79b095ec11f03`, chứa commit sửa PID Safety V3 `97c1e9df2d54314098066eca7c88c7e82edc4c79`; **chưa có FULL SOURCE ZIP V3 từ người dùng để kiểm thử toàn bộ**. Mọi kết luận 5 RED bên dưới chỉ áp dụng cho snapshot V2 đã ghim.
- Đã kiểm kê 1.003 file (227 `.py`, 34 `.ps1`, 16 `.tsx`, 93 `test_*.py`, tài liệu/audit lớn). Đã đọc các module đại diện của hệ thống, thực hiện quét file và kiểm thử độc lập trên source local. **Không tuyên bố đã rà từng dòng trong mọi file hoặc đã chạy physical lab.**

## Đánh giá kiến trúc

| Vùng | Kết luận | Rủi ro / cổng cần thêm |
|---|---|---|
| Backend FastAPI, SQLAlchemy, SQLite, Alembic | Có cơ chế test và cấu trúc module, app local | CI đầy đủ theo commit, check auth/CSRF và migration trong review |
| Frontend React/Vite/TypeScript | Có `npm run ci`, package lock, UI camera phân biệt MOCK/LIVE | Bắt buộc npm ci + typecheck/Vitest/build và API contract |
| Face pipeline YuNet/SFace | Có pin model & test model-real riêng | Không dùng unit model PASS làm thay camera thật; bảo vệ biometric/log |
| Camera RTSP EZVIZ / USB UVC | Có trust/camera revocation và mapping 1:1 trong nguồn mới | Source identity không đủ chứng minh frame; PnP serial/HMAC cấm xuất |
| COM/Windows | Đã có fix CoInitializeEx 1 arg, direct VT_BSTR Read và exactly-once release | Cần kiểm thử Windows PS 5.1 và runbook owner; không chỉ Linux |
| Process manager HF3 | Trong snapshot V2 đã xử lý PID con nhưng còn 5 negative failures; tip V3 mới hơn cần audit riêng | Cấm synthetic real kill; exact --app-dir; PID creation/session/no foreign kill |
| Evidence/release | Có FREEZE/CHANGED/FULL/SAFE EVIDENCE ZIP & hash | CI GitHub chưa có; check commit/tip drift và unsafe ZIP content |
| Git governance | Main chưa chứa mã nguồn | CI phải nằm đúng source branch; required checks sau khi có Actions run |

## Kiểm thử độc lập thực hiện

- COMPLETE ZIP: SHA256 đúng, 42 entries; FULL 1003 entries, CHANGED 26, SAFE-EVIDENCE 43; nested CRC và SHA256SUMS PASS.
- Existing HF3 targeted tests trên Linux tool environment: **26 PASS** (môi trường không phải Python 3.12/Windows production; không tương đương 521 agent tests).
- Guard framework tests: **8 PASS** (4 scaffolding + 4 ZIP verifier).
- Cursor Hook test: **23 PASS**.
- Combined Guard on uploaded source: **11 PASS, 5 FAIL** trong 16 pure Python assertions. Static `--strict`: 3 BLOCKER codes. Failures tái hiện đúng các lỗi nguy hiểm còn tồn tại, không phải crash môi trường.
- `windows-contract` trên Windows PowerShell 5.1, `backend-linux` full, `frontend` GitHub Actions: **UNRUN** cho bộ Guard mới vì chưa tích hợp repo; đòi check run thật. USB frame/soak/HMAC: **BLOCKED**.

## Root cause hệ thống

Agent tự viết code + tự viết test rồi báo PASS; phần giả lập WMI không cô lập thật `Stop-Process`; hợp đồng COM/PowerShell Windows không được kiểm tra trên runner Windows; nguồn ứng dụng và nhánh mặc định không thống nhất; phát hành bằng ZIP mà chưa có required status checks. Đây là thiếu cổng kiểm soát tự động, không phải thiếu MCP.

## Quyết định triển khai

`GUARD_FRAMEWORK=PASS_LOCAL`; `HF3_PID_SAFETY=BLOCKED`; `WINDOWS_CI=UNRUN`; `CAMERA_PHYSICAL=BLOCKED`.

Cho phép tích hợp Guard vào source-carrying branch. Reproduce 5 regression RED trên snapshot V2, rồi chạy cùng test ở tip mới nhất; nếu V3 đã GREEN thì không sửa lại code, nếu còn FAIL thì sửa tối thiểu; sau đó mới chạy CI và review. **Không Start HF3** trên Windows người dùng trước đó. Không dùng CI hay skill làm HMAC/signature vật lý.

## Tài liệu chính thức đã đối chiếu

- Cursor Rules: https://cursor.com/docs/rules
- Cursor Skills: https://cursor.com/docs/skills
- Cursor Hooks: https://cursor.com/docs/hooks
- GitHub Actions PowerShell: https://docs.github.com/en/actions/tutorials/build-and-test-code/powershell
- GitHub Rulesets: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets
- Pester 5 and PowerShell 5.1: https://pester.dev/docs/v5/introduction/installation
- PSScriptAnalyzer: https://learn.microsoft.com/en-us/powershell/utility-modules/psscriptanalyzer/overview
