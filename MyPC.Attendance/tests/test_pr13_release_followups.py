"""PR13 release-safety follow-ups: bootstrap, staged rollback, packaging scanner.

Synthetic temp DataDir only — never owner production DataDir.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, check_integrity
from app.core.schema_bootstrap import ALEMBIC_HEAD, assert_fastapi_supported, bootstrap_schema
from app.core.settings import AppSettings
from app.main import create_app
from app.models.entities import CameraDevice
from app.services.secret_fs_outbox import (
    _is_staged_leased,
    abort_outbox_after_rollback,
    queue_promote,
)
from app.services.secrets_store import SecretsStore


def test_clean_install_migrates_to_head_and_survives_second_boot(tmp_path: Path):
    settings = AppSettings(
        data_dir=tmp_path / "data",
        models_dir=tmp_path / "models",
        secret_key="audit-temp-synthetic-secret-1234567890123456",
        bootstrap_username="admin",
        bootstrap_password="TestAdminPass!234",
        require_password_change=False,
        app_env="development",
        demo_mode=True,
        database_url="sqlite:///" + str((tmp_path / "fresh.sqlite3").resolve()),
    )
    app1 = create_app(settings)
    with app1.state.container.session_factory() as db:
        version1 = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert app1.state.container.alembic_ok, app1.state.container.alembic_error
    assert version1 == ALEMBIC_HEAD, version1
    app2 = create_app(settings)
    with app2.state.container.session_factory() as db:
        version2 = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert app2.state.container.alembic_ok, app2.state.container.alembic_error
    assert version2 == ALEMBIC_HEAD, version2


def test_upgrade_pre_0010_preserves_camera_and_integrity(tmp_path: Path):
    """Existing DB stamped at 0008 must upgrade to HEAD without data loss."""
    db_path = tmp_path / "legacy.sqlite3"
    engine = create_engine("sqlite:///" + str(db_path.resolve()))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        db.add(
            CameraDevice(
                id=42,
                name="LegacyCam",
                host="192.0.2.42",
                enabled=True,
                mock_mode=True,
                created_at=datetime.now(timezone.utc),
                secret_generation=0,
                secret_ref="camera-42.bin",
            )
        )
        db.commit()
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('20261102_0008')"))
    settings = AppSettings(
        data_dir=tmp_path / "data",
        models_dir=tmp_path / "models",
        secret_key="audit-temp-synthetic-secret-1234567890123456",
        bootstrap_username="admin",
        bootstrap_password="TestAdminPass!234",
        require_password_change=False,
        app_env="development",
        demo_mode=True,
        database_url="sqlite:///" + str(db_path.resolve()),
    )
    secrets = SecretsStore(settings.data_dir)
    live_ref = secrets.put_camera_secret(42, "admin", "LegacyPassword!42")

    ok, err = bootstrap_schema(engine, settings)
    assert ok, err
    with engine.connect() as conn:
        ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        name = conn.execute(text("SELECT name FROM camera_devices WHERE id=42")).scalar()
        integrity = conn.execute(text("PRAGMA integrity_check")).scalar()
    assert ver == ALEMBIC_HEAD, ver
    assert name == "LegacyCam"
    assert integrity == "ok"
    assert secrets.has_secret(live_ref)
    assert secrets.get_camera_secret(live_ref)["password"] == "LegacyPassword!42"
    assert check_integrity(engine) == "ok"


def test_unknown_legacy_db_fails_closed_without_auto_stamp(tmp_path: Path):
    db_path = tmp_path / "unknown.sqlite3"
    engine = create_engine("sqlite:///" + str(db_path.resolve()))
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(64))"))
        conn.execute(text("INSERT INTO users (id, username) VALUES (1, 'legacy')"))
    settings = AppSettings(
        data_dir=tmp_path / "data",
        models_dir=tmp_path / "models",
        secret_key="audit-temp-synthetic-secret-1234567890123456",
        app_env="production",
        demo_mode=False,
        database_url="sqlite:///" + str(db_path.resolve()),
    )
    ok, err = bootstrap_schema(engine, settings)
    assert ok is False
    assert err and "alembic_version" in err
    with engine.connect() as conn:
        tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()}
    assert "alembic_version" not in tables


def test_failed_outbox_flush_leaves_no_staged_blob_or_lease(tmp_path: Path):
    engine = create_engine("sqlite:///" + str((tmp_path / "test.sqlite3").resolve()))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    secrets = SecretsStore(tmp_path / "data")
    with factory() as db:
        db.add(
            CameraDevice(
                id=999,
                name="Synthetic",
                host="192.0.2.9",
                enabled=True,
                mock_mode=True,
                created_at=datetime.now(timezone.utc),
                secret_generation=0,
            )
        )
        db.commit()
    live = secrets.put_camera_secret(999, "admin", "OriginalPassword!123")
    with factory() as db:
        staged = secrets.stage_camera_secret(999, "admin", "NewPassword!456")
        try:
            with patch.object(db, "flush", side_effect=RuntimeError("audit_synthetic_flush_failure")):
                queue_promote(db, staged_ref=staged, live_ref=live, camera_id=999, secrets=secrets)
        except RuntimeError:
            db.rollback()
            abort_outbox_after_rollback(secrets, db)
        assert secrets.get_camera_secret(live)["password"] == "OriginalPassword!123"
        assert not secrets.has_secret(staged), "orphan staged blob must be removed on rollback"
        assert not _is_staged_leased(secrets, staged), "staging lease must be released on rollback"


def test_fastapi_version_gate_matches_requirements():
    gate = assert_fastapi_supported()
    assert "fastapi_version" in gate
    assert gate["supported_range"] == ">=0.115.0,<0.116"
    # This CI/cloud image must run pinned 0.115.x
    assert gate["supported"] is True, gate


def test_sensitive_path_scanner_blocks_data_and_keys(tmp_path: Path):
    import zipfile
    import sys

    tools = Path(__file__).resolve().parents[1] / "tools"
    sys.path.insert(0, str(tools))
    from sensitive_path_scanner import forbidden_path, scan_zip_file

    assert forbidden_path("MyPC.Attendance/data/secrets/master.key")
    assert forbidden_path("foo/FIRST_RUN_ADMIN.txt")
    assert forbidden_path("x.sqlite3")
    assert not forbidden_path("backend/app/main.py")

    zpath = tmp_path / "dirty.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("MyPC.Attendance/backend/app/main.py", "# ok\n")
        zf.writestr("MyPC.Attendance/data/secrets/master.key", "DO_NOT_READ")
    denied = scan_zip_file(zpath)
    assert any("master.key" in d for d in denied)
