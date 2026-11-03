"""PR16-HF2: fail-closed release sensitive scanner — synthetic secret contaminates ZIP."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from tools.release_sensitive_scan import ScanFailure, scan_zip_bytes, would_fail_on_member


def test_synthetic_password_member_fails_scan():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "MyPC.Attendance/docs/leaked.txt",
            "password = 'SuperSecretValue99!!'\n",
        )
    with pytest.raises(ScanFailure) as ei:
        scan_zip_bytes(buf.getvalue())
    assert ei.value.rule == "GENERIC_PASSWORD_ASSIGN"
    assert "leaked.txt" in ei.value.path


def test_test_tree_password_fixture_allowed():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "MyPC.Attendance/tests/integration/example.py",
            'password = "CamSecret!99"\n',
        )
    scan_zip_bytes(buf.getvalue())  # allowed under tests/


def test_fixture_file_under_docs_path_still_fails():
    """Synthetic fixture content under a non-test path must block release."""
    fixture = Path(__file__).resolve().parents[1] / "fixtures/release_scan/synthetic_secret_fixture.txt"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("MyPC.Attendance/docs/oops.txt", fixture.read_text())
    with pytest.raises(ScanFailure):
        scan_zip_bytes(buf.getvalue())


def test_nested_zip_with_private_key_fails():
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        z.writestr("keys/id.pem", "-----BEGIN PRIVATE KEY-----\nABC\n-----END PRIVATE KEY-----\n")
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as z:
        z.writestr("bundle/inner.zip", inner.getvalue())
    with pytest.raises(ScanFailure) as ei:
        scan_zip_bytes(outer.getvalue())
    assert ei.value.rule == "PRIVATE_KEY_BLOCK"


def test_deny_path_data_dir():
    assert would_fail_on_member("MyPC.Attendance/data/secrets/x.bin", b"x") == "DENY_PATH"


def test_clean_source_member_ok():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("MyPC.Attendance/backend/app/hello.py", "print('ok')\n")
    scan_zip_bytes(buf.getvalue())  # no raise
