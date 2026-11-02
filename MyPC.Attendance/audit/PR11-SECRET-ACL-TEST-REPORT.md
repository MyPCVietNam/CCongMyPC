# Secrets ACL HF — test report

- **Base:** `4ec06cf467de06e911b68a0693025d50f6aaa2e5`
- **Linux pytest:** `cd MyPC.Attendance && .venv/bin/python -m pytest tests/ -q` → **265 passed**
- **ACL unit:** `tests/unit/test_pr11_secrets_acl.py` — fail-closed + no regenerate
- **Windows 10/11 physical matrix:** **BLOCKED** on this cloud agent (no Windows runner)
- **Camera HF regression:** preserved in suite (CRUD/credential/RTSP CONFIG_SAVED)
- **Physical gates:** CAMERA_LAB / FACE_PILOT / EXIT / INSTALLER remain **BLOCKED**
