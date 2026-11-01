"""Shared fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.clock import FrozenClock, local_wall  # noqa: E402
from app.core.permissions import DEMO_MOCK_INGEST, ENROLLMENT_MANAGE  # noqa: E402
from app.core.settings import AppSettings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.entities import User  # noqa: E402


@pytest.fixture
def work_day():
    return local_wall(2026, 3, 2, 0, 0, 0).date()  # Monday


@pytest.fixture
def frozen_clock():
    return FrozenClock(local_wall(2026, 3, 2, 12, 0, 0))


@pytest.fixture
def app_client(tmp_path, frozen_clock):
    """Development/demo client — mock ingest enabled + DEMO permission for admin."""
    settings = AppSettings(
        data_dir=tmp_path / "data",
        models_dir=tmp_path / "models",
        secret_key="test-secret-key-32-bytes-minimum!!",
        bootstrap_username="admin",
        bootstrap_password="TestAdminPass!234",
        require_password_change=False,
        app_env="development",
        demo_mode=True,
        allow_mock_observation=True,
        database_url=f"sqlite:///{(tmp_path / 'test.sqlite3').resolve()}",
    )
    application = create_app(settings=settings, clock=frozen_clock)
    # Grant demo + enrollment for P00/P01 automated tests
    factory = application.state.container.session_factory
    with factory() as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
        assert admin is not None
        admin.permissions_json = json.dumps([DEMO_MOCK_INGEST, ENROLLMENT_MANAGE])
        admin.must_change_password = False
        session.commit()
    with TestClient(application) as client:
        yield client, application


@pytest.fixture
def prod_client(tmp_path, frozen_clock):
    """Production-mode client — mock observation must be blocked."""
    settings = AppSettings(
        data_dir=tmp_path / "prod-data",
        models_dir=tmp_path / "prod-models",
        secret_key="test-secret-key-32-bytes-minimum!!",
        bootstrap_username="admin",
        bootstrap_password="TestAdminPass!234",
        require_password_change=False,
        app_env="production",
        demo_mode=False,
        allow_mock_observation=False,
        database_url=f"sqlite:///{(tmp_path / 'prod.sqlite3').resolve()}",
    )
    application = create_app(settings=settings, clock=frozen_clock)
    with TestClient(application) as client:
        yield client, application
