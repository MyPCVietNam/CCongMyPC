"""Windows ACL allowlist must accept app staged camera blobs (Gate 01 P0 hotfix).

Simulates the Windows branch of apply_new_secret_file_acl without requiring win32.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from app.core.windows_secrets_acl import (
    CAMERA_SECRET_RE,
    CAMERA_STAGED_SECRET_RE,
    apply_new_secret_file_acl,
    is_known_secret_name,
)
from app.services.secrets_store import SecretsStore


def _hex32(ch: str = "ab") -> str:
    # 32 lowercase hex chars
    base = (ch * 16)[:32]
    assert len(base) == 32
    return base


def test_camera_secret_regex_live_and_staged_precise():
    assert CAMERA_SECRET_RE.match("camera-1.bin")
    assert CAMERA_SECRET_RE.match("camera-99.bin")
    assert not CAMERA_SECRET_RE.match("camera-1.staged-" + _hex32() + ".bin")

    staged = f"camera-1.staged-{_hex32()}.bin"
    assert CAMERA_STAGED_SECRET_RE.match(staged)
    assert is_known_secret_name(staged)
    assert is_known_secret_name("camera-1.bin")

    # Rejects: wrong length, dashes UUID, uppercase, path smuggling, wildcards-as-name
    rejects = [
        f"camera-1.staged-{_hex32()[:31]}.bin",
        f"camera-1.staged-{_hex32()}0.bin",
        "camera-1.staged-123e4567-e89b-12d3-a456-426614174000.bin",
        f"camera-1.staged-{('A' * 32)}.bin",
        "camera-1.staged-*.bin",
        "camera-1.staged-../../etc/passwd.bin",
        "../camera-1.bin",
        "camera-1.bin.bak",
        "camera-.bin",
        "camera-1.STAGED-" + _hex32() + ".bin",
        "evil-camera-1.bin",
    ]
    for name in rejects:
        assert not is_known_secret_name(name), name
        assert CAMERA_SECRET_RE.match(name) is None
        assert CAMERA_STAGED_SECRET_RE.match(name) is None


def test_apply_new_secret_file_acl_windows_accepts_live_and_staged(tmp_path: Path):
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    live = secrets / "camera-7.bin"
    staged = secrets / f"camera-7.staged-{_hex32('cd')}.bin"
    live.write_bytes(b"x")
    staged.write_bytes(b"y")

    icacls_calls: list[list[str]] = []

    def fake_icacls(args, *, check):
        from app.core.windows_secrets_acl import AclCommandResult

        icacls_calls.append(list(args))
        return AclCommandResult(argv=["icacls", *args], returncode=0, stdout="", stderr="")

    with mock.patch("app.core.windows_secrets_acl.is_windows", return_value=True), mock.patch(
        "app.core.windows_secrets_acl.current_user_sid", return_value="S-1-5-21-1-2-3-1001"
    ), mock.patch(
        "app.core.windows_secrets_acl.ensure_secrets_dir_acl", return_value=[]
    ), mock.patch(
        "app.core.windows_secrets_acl._run_icacls", side_effect=fake_icacls
    ):
        apply_new_secret_file_acl(live)
        apply_new_secret_file_acl(staged)

    assert any(str(live) in c[0] for c in icacls_calls)
    assert any(str(staged) in c[0] for c in icacls_calls)


def test_apply_new_secret_file_acl_windows_rejects_invalid_names(tmp_path: Path):
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    bad = secrets / "camera-1.staged-nothex.bin"
    bad.write_bytes(b"z")
    with mock.patch("app.core.windows_secrets_acl.is_windows", return_value=True), mock.patch(
        "app.core.windows_secrets_acl.current_user_sid", return_value="S-1-5-21-1-2-3-1001"
    ):
        with pytest.raises(ValueError, match="allowlist"):
            apply_new_secret_file_acl(bad)


def test_stage_camera_secret_validates_and_writes(tmp_path: Path):
    store = SecretsStore(tmp_path)
    live = store.put_camera_secret(3, "admin", "LivePass!123")
    staged = store.stage_camera_secret(3, "admin", "StagedPass!456")
    assert CAMERA_SECRET_RE.match(live)
    assert CAMERA_STAGED_SECRET_RE.match(staged)
    assert store.has_secret(live)
    assert store.has_secret(staged)
    store.promote_staged_camera_secret(staged, live)
    assert store.get_camera_secret(live)["password"] == "StagedPass!456"
    assert not store.has_secret(staged)


def test_write_encrypted_scrubs_blob_when_windows_acl_fails(tmp_path: Path):
    store = SecretsStore(tmp_path)
    with mock.patch(
        "app.services.secrets_store.apply_new_secret_file_acl",
        side_effect=ValueError("không áp ACL cho tên không nằm trong allowlist: synthetic"),
    ):
        with pytest.raises(ValueError, match="allowlist"):
            store.stage_camera_secret(5, "admin", "ShouldNotRemain!1")
    leftovers = list((tmp_path / "secrets").glob("camera-5.staged-*.bin"))
    assert leftovers == [], "ACL failure must not leave unmanaged staged credential"


def test_validate_ref_rejects_non_allowlisted_names(tmp_path: Path):
    store = SecretsStore(tmp_path)
    with pytest.raises(ValueError):
        store._validate_ref("camera-1.staged-short.bin")
    with pytest.raises(ValueError):
        store._validate_ref("../camera-1.bin")
    store._validate_ref("camera-1.bin")
    store._validate_ref(f"camera-1.staged-{_hex32()}.bin")
