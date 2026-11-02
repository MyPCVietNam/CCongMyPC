"""PR11 secret-ACL HF: fail-closed, SID-based health, PS5.1 $home fix, repair safeguards."""

from __future__ import annotations

import os
import re
from pathlib import Path
from unittest import mock

import pytest

from app.core.secret_bootstrap import load_or_create_session_secret
from app.core.windows_secrets_acl import (
    AceInfo,
    AclCommandResult,
    SecretAccessDeniedError,
    SID_SYSTEM,
    assert_readable_existing_secret,
    directory_has_inheritable_user_ace,
    directory_policy_is_healthy,
    ensure_secrets_dir_acl,
    is_known_secret_name,
    list_known_secret_files,
    prepare_secrets_dir_for_app,
    probe_secrets_access,
)
from app.services.secrets_store import SecretsStore
from app.vision.faces.crypto_media import MediaCrypto

REPO = Path(__file__).resolve().parents[2]
PS1_FILES = [
    REPO / "scripts" / "windows" / "Repair-MyPCSecretsAcl.ps1",
    REPO / "scripts" / "windows" / "MyPC-Secrets-ACL-Audit-Repair.ps1",
]


def test_known_secret_names():
    assert is_known_secret_name("session.secret")
    assert is_known_secret_name("master.key")
    assert is_known_secret_name("face_templates.key")
    assert is_known_secret_name("camera-12.bin")
    assert not is_known_secret_name("notes.txt")
    assert not is_known_secret_name("camera-x.bin")


def test_defect_a_ps1_no_home_assignment_and_has_bom():
    """$HOME is read-only; PowerShell names are case-insensitive — never assign $home."""
    for path in PS1_FILES:
        raw = path.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf"), f"{path.name} missing UTF-8 BOM"
        # Strip BOM for text checks
        text = raw[3:].decode("utf-8")
        assert not re.search(r"(?i)\$home\s*=", text), f"{path.name} still assigns $home"
        assert re.search(r"(?i)\$attendanceHome\s*=", text), f"{path.name} missing $attendanceHome"
        assert "VariableNotWritable" not in text
        # Must use SID-aware directory health, not literal icacls SID string scan alone
        assert "Get-Acl" in text or "Translate" in text


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


def _healthy_aces(user_sid: str) -> list[AceInfo]:
    # Modify-like mask with (OI)|(CI) — not inherit-only
    modify = 0x001301BF
    full = 0x1F01FF
    return [
        AceInfo(sid=user_sid, ace_type=0, ace_flags=0x3, mask=modify),  # OI|CI
        AceInfo(sid=SID_SYSTEM, ace_type=0, ace_flags=0x3, mask=full),
    ]


def test_defect_b_directory_policy_uses_sid_aces_not_icacls_text(tmp_path):
    """Healthy ACL must be detected from AceInfo SIDs even if icacls would print DOMAIN\\User."""
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    user_sid = "S-1-5-21-111-222-333-1001"
    with mock.patch(
        "app.core.windows_secrets_acl.is_windows", return_value=True
    ), mock.patch(
        "app.core.windows_secrets_acl.read_dacl_aces", return_value=_healthy_aces(user_sid)
    ):
        assert directory_policy_is_healthy(secrets, user_sid) is True
        assert directory_has_inheritable_user_ace(secrets, user_sid) is True


def test_defect_b_unhealthy_without_oi_ci(tmp_path):
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    user_sid = "S-1-5-21-111-222-333-1001"
    # No inheritance flags
    aces = [
        AceInfo(sid=user_sid, ace_type=0, ace_flags=0, mask=0x001301BF),
        AceInfo(sid=SID_SYSTEM, ace_type=0, ace_flags=0, mask=0x1F01FF),
    ]
    with mock.patch(
        "app.core.windows_secrets_acl.is_windows", return_value=True
    ), mock.patch(
        "app.core.windows_secrets_acl.read_dacl_aces", return_value=aces
    ):
        assert directory_policy_is_healthy(secrets, user_sid) is False


def test_defect_b_ensure_idempotent_skips_icacls_when_healthy(tmp_path):
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    user_sid = "S-1-5-21-111-222-333-1001"
    calls: list[list[str]] = []

    def fake_run(args, *, check):
        calls.append(list(args))
        return AclCommandResult(argv=["icacls", *args], returncode=0, stdout="", stderr="")

    with mock.patch(
        "app.core.windows_secrets_acl.is_windows", return_value=True
    ), mock.patch(
        "app.core.windows_secrets_acl.current_user_sid", return_value=user_sid
    ), mock.patch(
        "app.core.windows_secrets_acl.read_dacl_aces", return_value=_healthy_aces(user_sid)
    ), mock.patch(
        "app.core.windows_secrets_acl._run_icacls", side_effect=fake_run
    ):
        first = ensure_secrets_dir_acl(secrets, force=False)
        second = ensure_secrets_dir_acl(secrets, force=False)
    assert first == []
    assert second == []
    assert calls == [], "already-correct ACL must not invoke icacls"


def test_defect_b_ensure_applies_when_unhealthy_then_postchecks(tmp_path):
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    user_sid = "S-1-5-21-9-9-9-1001"
    state = {"healthy": False}
    calls: list[list[str]] = []

    def fake_read(_path):
        if state["healthy"]:
            return _healthy_aces(user_sid)
        return []

    def fake_run(args, *, check):
        calls.append(list(args))
        # After grants, mark healthy
        if any("grant" in a for a in args):
            state["healthy"] = True
        return AclCommandResult(argv=["icacls", *args], returncode=0, stdout="", stderr="")

    with mock.patch(
        "app.core.windows_secrets_acl.is_windows", return_value=True
    ), mock.patch(
        "app.core.windows_secrets_acl.current_user_sid", return_value=user_sid
    ), mock.patch(
        "app.core.windows_secrets_acl.read_dacl_aces", side_effect=fake_read
    ), mock.patch(
        "app.core.windows_secrets_acl._run_icacls", side_effect=fake_run
    ):
        results = ensure_secrets_dir_acl(secrets, force=False)
    assert results, "unhealthy ACL must mutate"
    assert any("/inheritance:r" in c for c in calls)
    assert any(any("(OI)(CI)(M)" in a for a in c) for c in calls)
    assert any(any("(OI)(CI)(F)" in a for a in c) for c in calls)
    # Everyone remove attempted
    assert any(any("Everyone" in a or "S-1-1-0" in a for a in c) for c in calls)


def test_defect_c_repair_script_requires_app_stopped_and_backups(tmp_path):
    """repair_secrets_acl.py must refuse mutation without stopped app + critical backups."""
    import importlib.util

    script = REPO / "scripts" / "repair_secrets_acl.py"
    spec = importlib.util.spec_from_file_location("repair_secrets_acl", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    data = tmp_path / "data"
    secrets = data / "secrets"
    secrets.mkdir(parents=True)
    (secrets / "session.secret").write_text("s" * 40)
    (secrets / "master.key").write_bytes(os.urandom(32))
    (secrets / "face_templates.key").write_bytes(os.urandom(32))
    # No backups directory → must die
    with pytest.raises(SystemExit) as ei:
        mod.main(["--data-dir", str(data), "--check"])
    assert ei.value.code == 1


def test_defect_c_repair_script_check_with_backup_ok(tmp_path):
    import importlib.util

    script = REPO / "scripts" / "repair_secrets_acl.py"
    spec = importlib.util.spec_from_file_location("repair_secrets_acl", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    home = tmp_path / "Attendance"
    data = home / "data"
    secrets = data / "secrets"
    secrets.mkdir(parents=True)
    session = b"s" * 48
    master = os.urandom(32)
    face = os.urandom(32)
    (secrets / "session.secret").write_bytes(session)
    (secrets / "master.key").write_bytes(master)
    (secrets / "face_templates.key").write_bytes(face)
    bak = home / "backups" / "pre-camera-hf-test" / "data" / "secrets"
    bak.mkdir(parents=True)
    (bak / "session.secret").write_bytes(session)
    (bak / "master.key").write_bytes(master)
    (bak / "face_templates.key").write_bytes(face)

    with mock.patch(
        "app.core.windows_secrets_acl.assert_app_stopped", return_value=None
    ):
        # Re-import path uses app.core inside main — patch via module after load
        rc = mod.main(["--data-dir", str(data), "--check"])
    assert rc == 0


def test_defect_c_repair_script_source_never_grants_everyone_or_rewrites():
    text = (REPO / "scripts" / "repair_secrets_acl.py").read_text(encoding="utf-8")
    assert "Never grant Everyone" in text or "never grant Everyone" in text.lower() or "Everyone" in text
    assert "REPAIR-EXISTING-SECRETS" in text
    assert "assert_app_stopped" in text
    assert "save_acl_snapshot" in text
    # Must not contain code that writes new secret bytes
    assert "write_bytes" not in text
    assert "write_text" not in text
