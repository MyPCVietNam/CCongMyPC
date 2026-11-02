"""PR11 secret-ACL HF: fail-closed inaccessible secrets; never regenerate."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest import mock

import pytest

from app.core.secret_bootstrap import load_or_create_session_secret
from app.core.windows_secrets_acl import (
    SecretAccessDeniedError,
    assert_readable_existing_secret,
    is_known_secret_name,
    list_known_secret_files,
    prepare_secrets_dir_for_app,
    probe_secrets_access,
)
from app.services.secrets_store import SecretsStore
from app.vision.faces.crypto_media import MediaCrypto


def test_known_secret_names():
    assert is_known_secret_name("session.secret")
    assert is_known_secret_name("master.key")
    assert is_known_secret_name("face_templates.key")
    assert is_known_secret_name("camera-12.bin")
    assert not is_known_secret_name("notes.txt")
    assert not is_known_secret_name("camera-x.bin")


def test_session_secret_inaccessible_existing_raises(tmp_path):
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    path = secrets / "session.secret"
    path.write_text("a" * 48, encoding="utf-8")
    os.chmod(path, 0)

    def boom(*_a, **_k):
        raise PermissionError("denied")

    with mock.patch.object(Path, "open", boom):
        with pytest.raises(SecretAccessDeniedError) as ei:
            assert_readable_existing_secret(path)
        assert ei.value.code == "SECRET_ACCESS_DENIED"
        assert "session.secret" in str(ei.value)


def test_load_session_secret_does_not_regenerate_unreadable(tmp_path):
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    path = secrets / "session.secret"
    original = "persistent-session-secret-value-32bytes-min!!"
    path.write_text(original, encoding="utf-8")
    before = path.read_bytes()

    with mock.patch(
        "app.core.secret_bootstrap.assert_readable_existing_secret",
        side_effect=SecretAccessDeniedError(path),
    ):
        with pytest.raises(SecretAccessDeniedError):
            load_or_create_session_secret(
                tmp_path,
                env_value=None,
                app_env="production",
                demo_mode=False,
            )
    assert path.read_bytes() == before


def test_face_templates_key_permission_never_regenerates(tmp_path):
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    key_path = secrets / "face_templates.key"
    original = os.urandom(32)
    key_path.write_bytes(original)

    with mock.patch(
        "app.vision.faces.crypto_media.assert_readable_existing_secret",
        side_effect=SecretAccessDeniedError(key_path),
    ):
        with pytest.raises(SecretAccessDeniedError):
            MediaCrypto(tmp_path)
    assert key_path.read_bytes() == original


def test_master_key_permission_never_regenerates(tmp_path):
    # Create a valid store first
    store = SecretsStore(tmp_path)
    key_path = tmp_path / "secrets" / "master.key"
    original = key_path.read_bytes()
    del store

    with mock.patch(
        "app.services.secrets_store.assert_readable_existing_secret",
        side_effect=SecretAccessDeniedError(key_path),
    ):
        with pytest.raises(SecretAccessDeniedError):
            SecretsStore(tmp_path)
    assert key_path.read_bytes() == original


def test_probe_report_redacts_and_lists(tmp_path):
    SecretsStore(tmp_path)
    MediaCrypto(tmp_path)
    load_or_create_session_secret(
        tmp_path,
        env_value=None,
        app_env="development",
        demo_mode=True,
        allow_ephemeral_dev=True,
    )
    report = probe_secrets_access(tmp_path)
    assert report.secrets_redacted is True
    names = {f["name"] for f in report.files}
    assert "master.key" in names
    assert "face_templates.key" in names
    assert "session.secret" in names
    blob = str(report.__dict__)
    # Must not contain raw key material from files
    assert (tmp_path / "secrets" / "master.key").read_bytes().decode("latin-1") not in blob


def test_prepare_secrets_lists_known_only(tmp_path):
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "session.secret").write_text("x" * 40)
    (secrets / "notes.txt").write_text("nope")
    (secrets / "camera-3.bin").write_bytes(b"\0" * 16)
    prepare_secrets_dir_for_app(tmp_path)
    names = [p.name for p in list_known_secret_files(secrets)]
    assert "session.secret" in names
    assert "camera-3.bin" in names
    assert "notes.txt" not in names


def test_new_session_secret_bytes_stable_across_reloads(tmp_path):
    a = load_or_create_session_secret(
        tmp_path, env_value=None, app_env="development", demo_mode=True, allow_ephemeral_dev=True
    )
    b = load_or_create_session_secret(
        tmp_path, env_value=None, app_env="development", demo_mode=True, allow_ephemeral_dev=True
    )
    assert a == b
    assert (tmp_path / "secrets" / "session.secret").read_text(encoding="utf-8").strip() == a
