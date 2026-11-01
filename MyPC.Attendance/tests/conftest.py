"""Shared fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.clock import FrozenClock, local_wall  # noqa: E402
from app.core.settings import AppSettings  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
def work_day():
    return local_wall(2026, 3, 2, 0, 0, 0).date()  # Monday


@pytest.fixture
def frozen_clock():
    return FrozenClock(local_wall(2026, 3, 2, 12, 0, 0))


@pytest.fixture
def app_client(tmp_path, frozen_clock):
    settings = AppSettings(
        data_dir=tmp_path / "data",
        secret_key="test-secret-key-32-bytes-minimum!!",
        bootstrap_username="admin",
        bootstrap_password="TestAdminPass!234",
        database_url=f"sqlite:///{(tmp_path / 'test.sqlite3').resolve()}",
    )
    application = create_app(settings=settings, clock=frozen_clock)
    with TestClient(application) as client:
        yield client, application
