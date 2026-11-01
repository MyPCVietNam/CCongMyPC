# MyPC Attendance

Hệ thống chấm công offline-first bằng camera IP EZVIZ cho MyPC Việt Nam.

**Phiên bản đặc tả:** v1.5  
**Trạng thái hiện tại:** P00 (Source/License Audit + Camera Gateway + Working Web Shell)

## Yêu cầu phát triển

- Python 3.12+
- Node.js 20+ (chỉ khi build frontend)
- Hệ điều hành: Linux (dev) / Windows 10/11 x64 (mục tiêu triển khai)

## Khởi chạy nhanh (chế độ mô phỏng)

```bash
cd MyPC.Attendance
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
pip install -r backend/requirements-dev.txt
cd frontend && npm install && npm run build && cd ..
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8765
```

Mở trình duyệt: http://127.0.0.1:8765

Tài khoản lần đầu: xem hướng dẫn bootstrap trong `docs/deployment/first-run.md`.

## Kiểm thử

```bash
cd MyPC.Attendance
source .venv/bin/activate
pytest tests/unit tests/integration -v --tb=short
```

## Cấu trúc

Xem `docs/architecture.md` và các ADR trong `docs/adr/`.

## Giấy phép

Mã nguồn sản phẩm: MIT (xem `/LICENSE` ở gốc kho).  
Thành phần bên thứ ba: `docs/THIRD_PARTY_NOTICES.md`.

## Lưu ý quan trọng

- Không tính lương / bảo hiểm / phạt tiền lương.
- Chế độ Mock Camera độc lập với kiểm thử camera thật.
- Cửa sổ nhận diện chiều: **17:00–23:55** (không phải 19:00). Mốc tham chiếu 18:00.
