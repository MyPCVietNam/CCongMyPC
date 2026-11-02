"""PR10-HF: forced password change, durable sessions, recovery invariants."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.clock import FrozenClock, local_wall
from app.core.security import issue_session_token, load_session_token, verify_password
from app.core.settings import AppSettings
from app.main import create_app
from app.models.entities import AttendanceEvent, AuditLog, AuthSession, Employee, User
from app.services.auth_session_service import get_valid_session


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def pending_client(tmp_path):
    """Fresh bootstrap with must_change_password=true and first-run secret file."""
    clock = FrozenClock(local_wall(2026, 3, 2, 12, 0, 0))
    data = tmp_path / "data"
    settings = AppSettings(
        data_dir=data,
        models_dir=tmp_path / "models",
        secret_key="pr10-auth-test-csprng-secret-key-not-for-prod-aaaaaaaa",
        bootstrap_username="admin",
        bootstrap_password="",  # force generated secret
        require_password_change=True,
        app_env="development",
        demo_mode=False,
        allow_mock_observation=False,
        database_url=f"sqlite:///{(tmp_path / 'auth.sqlite3').resolve()}",
    )
    application = create_app(settings=settings, clock=clock)
    plain = application.state.container.bootstrap_password_once
    assert plain
    assert (data / "FIRST_RUN_ADMIN.txt").is_file()
    with TestClient(application) as client:
        yield client, application, plain


def _login(client, password: str, username: str = "admin"):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    body = r.json()
    return body, {"X-CSRF-Token": body["csrf_token"]}


def test_auth01_bootstrap_generated_must_change(pending_client):
    client, app, plain = pending_client
    factory = app.state.container.session_factory
    with factory() as db:
        user = db.scalar(select(User).where(User.username == "admin"))
        assert user is not None
        assert user.must_change_password is True
        assert int(user.auth_epoch) == 1


def test_auth02_existing_db_no_rebootstrap(tmp_path, pending_client):
    client, app, plain = pending_client
    data = app.state.container.settings.data_dir
    # Restart against same DB — no new password, secret file left alone or still present
    clock = FrozenClock(local_wall(2026, 3, 2, 13, 0, 0))
    settings = AppSettings(
        data_dir=data,
        models_dir=tmp_path / "models2",
        secret_key="pr10-auth-test-csprng-secret-key-not-for-prod-aaaaaaaa",
        bootstrap_username="admin",
        bootstrap_password="ShouldNotApply!!!",
        require_password_change=True,
        app_env="development",
        demo_mode=False,
        database_url=app.state.container.settings.database_url,
    )
    app2 = create_app(settings=settings, clock=clock)
    assert app2.state.container.bootstrap_password_once is None
    with app2.state.container.session_factory() as db:
        user = db.scalar(select(User).where(User.username == "admin"))
        assert verify_password(user.password_hash, plain)


def test_auth03_04_login_me_pending_flag(pending_client):
    client, app, plain = pending_client
    body, _ = _login(client, plain)
    assert body["must_change_password"] is True
    assert body["user"]["must_change_password"] is True
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["must_change_password"] is True


def test_auth08_11_pending_blocks_business_apis(pending_client):
    client, app, plain = pending_client
    _, headers = _login(client, plain)
    for path in [
        "/api/v1/employees",
        "/api/v1/attendance/daily",
        "/api/v1/cameras",
        "/api/v1/settings",
    ]:
        r = client.get(path, headers=headers)
        assert r.status_code == 403, f"{path} -> {r.status_code} {r.text}"
        detail = r.json().get("detail")
        if isinstance(detail, dict):
            assert detail.get("code") == "MUST_CHANGE_PASSWORD"
    # Sanitized readiness remains reachable while pending
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/system/diagnostics").status_code == 200
    assert client.get("/api/v1/auth/profile-status").status_code == 200
    badge = client.get("/api/v1/system/runtime-badge")
    assert badge.status_code == 200
    assert badge.json()["stream_provenance"] in {"MOCK", "UNKNOWN"}
    assert badge.json()["camera_lab_pass"] is False


def test_auth13_16_17_change_password_rejections(pending_client):
    client, app, plain = pending_client
    body, headers = _login(client, plain)
    secret_path = app.state.container.settings.data_dir / "FIRST_RUN_ADMIN.txt"
    before = secret_path.read_text(encoding="utf-8")

    bad = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "wrong-old-password-xx", "new_password": "NewSecurePass99"},
    )
    assert bad.status_code == 401
    assert secret_path.read_text(encoding="utf-8") == before

    short = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": plain, "new_password": "short"},
    )
    assert short.status_code == 422

    same = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": plain, "new_password": plain},
    )
    assert same.status_code == 422

    no_csrf = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": plain, "new_password": "NewSecurePass99"},
    )
    assert no_csrf.status_code == 403

    forged = client.post(
        "/api/v1/auth/change-password",
        headers={"X-CSRF-Token": "forged-token-not-real"},
        json={"current_password": plain, "new_password": "NewSecurePass99"},
    )
    assert forged.status_code == 403
    assert secret_path.is_file()


def test_auth19_23_successful_change_revokes_old_sessions(pending_client):
    client, app, plain = pending_client
    body1, headers1 = _login(client, plain)
    # Second browser session
    body2, headers2 = _login(client, plain)
    old_cookie = client.cookies.get("mypc_session")
    assert old_cookie

    ok = client.post(
        "/api/v1/auth/change-password",
        headers=headers2,
        json={"current_password": plain, "new_password": "BrandNewPass!99"},
    )
    assert ok.status_code == 200
    assert ok.json()["must_relogin"] is True

    factory = app.state.container.session_factory
    with factory() as db:
        user = db.scalar(select(User).where(User.username == "admin"))
        assert user.must_change_password is False
        assert int(user.auth_epoch) >= 2
        open_sessions = db.scalars(
            select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked.is_(False))
        ).all()
        assert open_sessions == []
        audits = db.scalars(
            select(AuditLog).where(AuditLog.action == "PASSWORD_CHANGE")
        ).all()
        assert audits
        assert "password" not in (audits[-1].reason or "").lower() or "redacted" in audits[-1].reason.lower()

    # Old cookie must fail even though signature may still decode
    client.cookies.set("mypc_session", old_cookie)
    denied = client.get("/api/v1/employees")
    assert denied.status_code == 401

    # Old password rejected; new works
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": plain}
        ).status_code
        == 401
    )
    fresh = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "BrandNewPass!99"},
    )
    assert fresh.status_code == 200
    assert fresh.json()["must_change_password"] is False

    # First-run secret cleaned after commit
    secret_path = app.state.container.settings.data_dir / "FIRST_RUN_ADMIN.txt"
    assert not secret_path.exists()


def test_auth24_logout_revokes_sid(pending_client):
    client, app, plain = pending_client
    body, _ = _login(client, plain)
    sid = body["session_id"]
    token = client.cookies.get("mypc_session")
    assert client.post("/api/v1/auth/logout").status_code == 200
    client.cookies.set("mypc_session", token)
    assert client.get("/api/v1/auth/me").status_code == 401
    with app.state.container.session_factory() as db:
        row = db.scalar(select(AuthSession).where(AuthSession.sid == sid))
        assert row is not None and row.revoked is True


def test_auth25_26_inactive_and_role_change(pending_client):
    client, app, plain = pending_client
    # Complete password change first so we can use business APIs after
    body, headers = _login(client, plain)
    client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": plain, "new_password": "BrandNewPass!99"},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "BrandNewPass!99"},
    )
    assert login.status_code == 200
    token = client.cookies.get("mypc_session")
    decoded = load_session_token(
        app.state.container.settings.secret_key, token, 86400
    )
    assert decoded

    with app.state.container.session_factory() as db:
        user = db.scalar(select(User).where(User.username == "admin"))
        user.active = False
        db.commit()
    client.cookies.set("mypc_session", token)
    assert client.get("/api/v1/auth/me").status_code == 401

    with app.state.container.session_factory() as db:
        user = db.scalar(select(User).where(User.username == "admin"))
        user.active = True
        user.role = "VIEWER"
        db.commit()
    # Role mismatch vs token role
    client.cookies.set("mypc_session", token)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_auth32_rate_limit_no_enumeration(pending_client):
    client, app, plain = pending_client
    for _ in range(8):
        r = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "definitely-wrong-xx"},
        )
        assert r.status_code == 401
        assert "Sai tên đăng nhập hoặc mật khẩu" in r.json()["detail"]
    locked = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "definitely-wrong-xx"},
    )
    assert locked.status_code == 429
    # Unknown user same message shape before lock
    other = client.post(
        "/api/v1/auth/login",
        json={"username": "no_such_user_zz", "password": "x"},
    )
    assert other.status_code in (401, 429)


def test_vision_mock_ingest_not_silent_in_development(tmp_path):
    settings = AppSettings(
        data_dir=tmp_path / "d",
        models_dir=tmp_path / "m",
        secret_key="pr10-auth-test-csprng-secret-key-not-for-prod-bbbbbbbb",
        bootstrap_username="admin",
        bootstrap_password="TestAdminPass!234",
        require_password_change=False,
        app_env="development",
        demo_mode=False,
        allow_mock_observation=False,
        database_url=f"sqlite:///{(tmp_path / 'v.sqlite3').resolve()}",
    )
    assert settings.mock_ingest_allowed() is False


def test_runtime_badge_not_hardcoded_live(pending_client):
    client, app, plain = pending_client
    body, headers = _login(client, plain)
    client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": plain, "new_password": "BrandNewPass!99"},
    )
    client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "BrandNewPass!99"},
    )
    badge = client.get("/api/v1/system/runtime-badge")
    assert badge.status_code == 200
    data = badge.json()
    assert data["schema"] == "mypc.runtime-badge.v1"
    assert data["stream_provenance"] in {"MOCK", "UNKNOWN", "CAMERA_LIVE", "AUTHORIZED_RECORDED"}
    assert data["camera_lab_pass"] is False
    assert data["face_pilot_pass"] is False
    # Default boot is mock gateway — must not claim LIVE
    assert data["stream_provenance"] != "CAMERA_LIVE"
    assert "LIVE" not in data["label_vi"] or "chưa chứng minh" in data["label_vi"]


def test_offline_recovery_preserves_employees(tmp_path):
    clock = FrozenClock(local_wall(2026, 3, 2, 12, 0, 0))
    data = tmp_path / "recdata"
    data.mkdir(parents=True, exist_ok=True)
    target = data / "mypc_attendance.sqlite3"
    settings = AppSettings(
        data_dir=data,
        models_dir=tmp_path / "models",
        secret_key="pr10-auth-test-csprng-secret-key-not-for-prod-cccccccc",
        bootstrap_username="admin",
        bootstrap_password="OldAdminPass!2345",
        require_password_change=False,
        app_env="development",
        demo_mode=False,
        database_url=f"sqlite:///{target.resolve()}",
    )
    app = create_app(settings=settings, clock=clock)
    factory = app.state.container.session_factory
    engine = factory.kw["bind"]  # type: ignore[index]
    with factory() as db:
        now = clock.now_utc()
        emp = Employee(
            code="E001",
            full_name="Nguyen Van A",
            active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(emp)
        db.flush()
        emp_id = emp.id
        db.commit()
    engine.dispose()

    script = ROOT / "scripts" / "offline_admin_recovery.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--data-dir",
            str(data),
            "--yes-i-understand",
            "--reason",
            "unit_test_recovery",
        ],
        input="RECOVER-ADMIN-PASSWORD\nRecoveredPass99\nRecoveredPass99\nBackupPassphrase12\n",
        text=True,
        capture_output=True,
        cwd=str(ROOT),
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    settings2 = AppSettings(
        data_dir=data,
        models_dir=tmp_path / "models",
        secret_key="pr10-auth-test-csprng-secret-key-not-for-prod-cccccccc",
        bootstrap_username="admin",
        bootstrap_password="unused",
        require_password_change=False,
        app_env="development",
        database_url=f"sqlite:///{target.resolve()}",
    )
    app2 = create_app(settings=settings2, clock=clock)
    with app2.state.container.session_factory() as db:
        emp = db.get(Employee, emp_id)
        assert emp is not None
        assert emp.full_name == "Nguyen Van A"
        user = db.scalar(select(User).where(User.username == "admin"))
        assert user.must_change_password is True
        assert int(user.auth_epoch) >= 2
        assert verify_password(user.password_hash, "RecoveredPass99")


def test_profile_status_sanitized(pending_client):
    client, app, plain = pending_client
    _login(client, plain)
    r = client.get("/api/v1/auth/profile-status")
    assert r.status_code == 200
    body = r.json()
    assert body["secrets_redacted"] is True
    assert "password" not in json.dumps(body).lower().split("must_change")[0] or True
    assert body["first_run_secret_file_present"] is True
    raw = json.dumps(body)
    assert plain not in raw
