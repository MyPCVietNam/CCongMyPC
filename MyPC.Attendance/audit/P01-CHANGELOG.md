# P01 CHANGELOG

## Added

- Face pipeline: YuNet detector, SFace embedder, quality, matcher, encrypted AES-GCM template store
- Enrollment APIs + Vietnamese Đăng ký khuôn mặt wizard (DEMO/fixture)
- `tools/fetch_models.py` download/import/verify with real SHA256
- Alembic migration 20261102_0001
- Windows PowerShell camera lab scripts + `docs/vi/windows-camera-lab.md`
- P00-HF security suite

## Notes

- REAL_CAMERA enrollment returns CAMERA_LAB_BLOCKED until live lab pass
- Synthetic verify cannot publish to production attendance
- Weights gitignored; offline import supported
