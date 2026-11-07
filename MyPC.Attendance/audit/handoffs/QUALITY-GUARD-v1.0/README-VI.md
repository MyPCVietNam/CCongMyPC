# MyPC Engineering Quality Guard v1.0 — Hướng dẫn sử dụng

**Dành cho:** https://github.com/MyPCVietNam/CCongMyPC  
**Giai đoạn:** Chặn lỗi trước khi chạy HF3 trên Windows thật. **KHÔNG** phải bản cập nhật ứng dụng, không cài camera, không tự Start/Stop/Prepare, không động DataDir/HMAC.

## Bên trong gói

- `repository-overlay/`: đặt nguyên cấu trúc này lên **gốc Git repository CCongMyPC**, không phải thư mục `MyPC.Attendance/`.
  - `AGENTS.md`: hợp đồng không thay đổi giữa các lượt Cursor.
  - `.cursor/rules/*.mdc`: quy tắc core, Windows PID/PowerShell, camera identity/COM, backend/security, test/release, frontend.
  - `.cursor/skills/mypc-safe-change/SKILL.md`: quy trình RED→GREEN→CI→independent review→ZIP.
  - `.cursor/hooks.json` và `.cursor/hooks/*.cjs`: chặn các lệnh nguy hiểm từ terminal agent, failClosed, có 23 unit tests.
  - `.github/workflows/mypc-quality-guard.yml`: 4 jobs Linux backend, Windows PS 5.1, frontend, Guard.
  - `quality_guard/`: pure Python contracts, 8 framework/ZIP tests, 8 HF3 negative/positive tests, Pester read-only checks, ZIP verifier.
  - `MyPC.Attendance/docs/quality`: known blockers, release checklist, gates.
- `INSTALL-QUALITY-GUARD.ps1`: chế độ PREVIEW mặc định; chỉ sao chép file mới khi có `-Apply`, không ghi đè hoặc xóa bất kỳ file đang tồn tại nào.
- `CURSOR-IMPLEMENTATION-PROMPT-EN.md`: prompt duy nhất gửi Cursor cùng gói ZIP.
- `PROJECT-AUDIT-VI.md`: phát hiện, kiểm thử, giới hạn xác minh.
- `SHA256SUMS.txt`: hash mọi file trong gói (trừ chính SHA256SUMS); gói bên ngoài có thêm SHA256 riêng khi bàn giao.

## A. Cách dùng đơn giản nhất: qua Cursor

1. Tải và gửi toàn bộ `MYPC-ENGINEERING-QUALITY-GUARD-v1.0.zip` cho Cursor, kèm **nội dung** `CURSOR-IMPLEMENTATION-PROMPT-EN.md`. Đảm bảo Cursor có quyền làm việc trên đúng repository `MyPCVietNam/CCongMyPC`.
2. Yêu cầu Cursor xác minh branch/HEAD hiện tại. Tại thời điểm audit, PR #27 dùng branch `cursor/p02-usb-hf3-dshow-com-enum-83a8` với base `cursor/p02-usb-hf2-verified-binding-83a8`. **Không được mặc định dùng `main`** vì main mới có LICENSE; branch có thể đã thay đổi sau khi đóng gói.
3. Cursor tích hợp **toàn bộ `repository-overlay/`** vào gốc repo, không thay đổi/sửa chéo chức năng camera. Mỗi file trong overlay giữ nguyên path. Không đụng dữ liệu chủ sở hữu.
4. Cursor chạy selftests của Guard; sau đó `--strict` và regression HF3. **Baseline snapshot V2: 5 FAIL / 3 blocker codes**. PR #27 đã có commit V3 mới hơn; hãy chạy cùng test trên **HEAD hiện tại**. Nếu V3 đã GREEN thì không sửa lại code, nếu còn FAIL mới sửa; tuyệt đối không xóa hoặc `skip` bài test.
5. Chờ GitHub Actions chạy trên commit mới. Nếu 4 job `guard-contract`, `backend-linux`, `frontend`, `windows-contract` chưa PASS, không merge. Test Windows là PowerShell 5.1/Pester (không phải camera thật).
6. Khi 4 jobs PASS, yêu cầu review độc lập, xuất FULL/CHANGED/EVIDENCE/COMPLETE ZIP kèm SHA256. Gửi COMPLETE ZIP lại đây để tôi audit độc lập. Chỉ sau đó mới tính tới owner camera lab.

## B. Cài thủ công vào Git checkout đã có source (Windows)

**Chỉ thực hiện trong thư mục clone Git chứa `MyPC.Attendance/backend/app/main.py`.** Nếu thư mục chỉ có LICENSE, script sẽ từ chối.

```powershell
# 1. Giải nén ZIP, giữ nguyên thư mục repository-overlay nằm cạnh script cài.
$package = "$env:USERPROFILE\Downloads\MYPC-ENGINEERING-QUALITY-GUARD-v1.0"
$repo = 'D:\Code\CCongMyPC'  # Đổi thành đường dẫn Git checkout thực tế có toàn bộ source

# 2. Chỉ xem trước; KHÔNG ghi file
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$package\INSTALL-QUALITY-GUARD.ps1" -RepoRoot $repo

# 3. Sau khi xem danh sách PREVIEW_ADD và xác nhận repo đúng, mới sao chép
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$package\INSTALL-QUALITY-GUARD.ps1" -RepoRoot $repo -Apply

# 4. Kiểm tra thay đổi trước khi tạo PR
cd $repo
git status --short
```

Script KHÔNG làm `git commit/push`, không ghi đè file trùng tên có hash khác, không xóa và không mở camera.

## C. Các lệnh kiểm thử an toàn (trong gốc Git repository)

```powershell
python -m unittest discover -s quality_guard/tests -p 'test_*.py' -v
python quality_guard/check.py --root . --strict
node --test .cursor/hooks/guard-shell.test.cjs
```

`--strict` trả mã lỗi 2 trên snapshot V2 đã ghim là đúng; trên mã V3 mới hơn cần đo lại. Bản cũ RED không có nghĩa HEAD mới chắc chắn còn lỗi. **Không chạy** `p02_usb_hf3_pid_safety_runtime_tests.ps1` cũ hoặc `-Mode Start` trong giai đoạn cài Guard.

Sau khi tích hợp và sửa, CI trên GitHub sẽ chạy tự động. Không cần cài Pester thủ công cho CI vì workflow cài phiên bản phù hợp trên Windows runner. Nếu Windows Actions không chạy do repository setting/quyền hạn, cần bật Actions và kiểm tra kết quả thật trước khi merge.

## D. Bảo vệ branch/PR trên GitHub

Khi 4 jobs đã xuất hiện trong tab Checks: vào GitHub repository → Settings → Rules → Rulesets (hoặc Branch protection); áp dụng cho branch đích, yêu cầu `guard-contract`, `backend-linux`, `frontend`, `windows-contract`, pull request review, không force-push, không bypass. Đặt expected source là GitHub Actions nếu có lựa chọn. `main` chỉ có LICENSE không thay thế bảo vệ nhánh có source.

**Lưu ý:** Rules / Hooks là hướng dẫn hoặc cổng chặn trong Cursor, không phải sandbox an toàn tuyệt đối. CI và mã kiểm thử thuần được thiết kế không thể coi lỗi PID/COM là PASS khi chưa sửa.

## E. Sau này sử dụng ra sao?

Với mỗi sửa lỗi, chỉ cần nói Cursor: `Use /mypc-safe-change. Make a baseline RED regression, implement minimal fix, run all required CI and release a verified COMPLETE-AUDIT ZIP. Never run owner physical scripts.`

Cursor sẽ đọc Rules và Skill trong repo. Cứ gửi COMPLETE ZIP cho tôi để audit. Nếu bạn muốn dùng Skill riêng trong ChatGPT, cài file `skill.zip` của bộ bàn giao vào thư viện Skills qua `/skills`; nó chuẩn hóa quy trình audit độc lập, nhưng không tự thay đổi repository hoặc chạy CI.

## F. Khi nào được thử lại HF3 camera?

Chỉ sau khi PID-safety regression và 4 GitHub jobs đều GREEN, đồng thời review độc lập không còn lỗi nghiêm trọng. Sau đó owner mới chạy runbook riêng trên môi trường HF3 `127.0.0.1:18878`. Không làm xáo trộn `18876/18877`, DataDir, HMAC; điều kiện CAMERA_LAB vẫn chưa PASS cho đến khi có video frame và owner sign-off.

**Không có phương án nào bảo đảm tuyệt đối 100% không lỗi; đây là cách giảm lỗi bằng bằng chứng và cổng chặn thực tế, thay vì chỉ yêu cầu AI 'cẩn thận'.**
