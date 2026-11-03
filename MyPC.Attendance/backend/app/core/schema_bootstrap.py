"""Non-destructive SQLite/Alembic bootstrap — fresh install vs existing DB.

Never auto-stamp an unknown legacy database. Never treat create_all as a
migration repair that pretends Alembic succeeded.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.core.database import Base
from app.core.settings import AppSettings

logger = logging.getLogger(__name__)

ALEMBIC_HEAD = "20261103_0012"


def _alembic_config(settings: AppSettings):
    from alembic.config import Config

    # schema_bootstrap.py lives at backend/app/core/ — alembic.ini is at MyPC.Attendance/
    here = Path(__file__).resolve()
    project_root = here.parents[3]  # MyPC.Attendance
    backend_root = here.parents[2]
    candidates = [
        project_root / "alembic.ini",
        backend_root / "alembic.ini",
    ]
    ini = next((p for p in candidates if p.exists()), None)
    if ini is None:
        return None
    script_dir = backend_root / "alembic"
    if not script_dir.is_dir():
        # ini may declare script_location=backend/alembic relative to project root
        alt = project_root / "backend" / "alembic"
        script_dir = alt if alt.is_dir() else script_dir
    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(script_dir))
    cfg.set_main_option("sqlalchemy.url", settings.resolved_database_url())
    return cfg


def current_alembic_version(engine: Engine) -> str | None:
    inspector = inspect(engine)
    if "alembic_version" not in inspector.get_table_names():
        return None
    with engine.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        return str(row[0]) if row else None


def _table_names(engine: Engine) -> set[str]:
    inspector = inspect(engine)
    return {t for t in inspector.get_table_names() if not t.startswith("sqlite_")}


def bootstrap_schema(engine: Engine, settings: AppSettings) -> tuple[bool, str | None]:
    """
    Returns (alembic_ok, error_message).

    - Empty DB: create_all + stamp HEAD (fresh bootstrap). Migrations 0001–0008
      are incremental HF patches that assume a prior base schema.
    - DB with alembic_version: upgrade to head; create_all only fills missing
      ORM tables (non-destructive).
    - DB with tables but no alembic_version: fail closed (no auto-stamp).
    """
    tables = _table_names(engine)
    app_tables = tables - {"alembic_version"}
    has_version = "alembic_version" in tables
    cfg = _alembic_config(settings)
    if cfg is None:
        # No alembic.ini — best-effort create_all only (dev packaging edge)
        Base.metadata.create_all(engine)
        return False, "alembic.ini missing"

    from alembic import command

    if not app_tables and not has_version:
        # ----- Fresh empty database -----
        try:
            Base.metadata.create_all(engine)
            command.stamp(cfg, "head")
            ver = current_alembic_version(engine)
            if ver != ALEMBIC_HEAD:
                return False, f"fresh stamp expected {ALEMBIC_HEAD}, got {ver!r}"
            logger.info("schema_bootstrap_fresh stamped head=%s", ver)
            return True, None
        except Exception as exc:  # noqa: BLE001
            return False, f"fresh bootstrap failed: {exc}"

    if has_version:
        # ----- Known migration chain -----
        try:
            command.upgrade(cfg, "head")
            # Non-destructive: add any new ORM tables not yet in migrations
            Base.metadata.create_all(engine)
            ver = current_alembic_version(engine)
            if ver != ALEMBIC_HEAD:
                return False, f"upgrade left version {ver!r}, expected {ALEMBIC_HEAD}"
            logger.info("schema_bootstrap_upgrade head=%s", ver)
            return True, None
        except Exception as exc:  # noqa: BLE001
            return False, f"Alembic migration failed: {exc}"

    # ----- Unknown legacy: tables without alembic_version -----
    sample = sorted(app_tables)[:8]
    msg = (
        "Database has application tables but no alembic_version row. "
        "Refusing auto-stamp (data-loss risk). Backup DataDir, then run a "
        f"controlled migration. tables_sample={sample}"
    )
    logger.error("schema_bootstrap_unknown_legacy %s", msg)
    return False, msg


def assert_fastapi_supported() -> dict[str, Any]:
    """Release/installer gate: refuse unsupported FastAPI majors for C13 semantics."""
    import fastapi

    ver = getattr(fastapi, "__version__", "0")
    parts = ver.split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1])
    except (ValueError, IndexError):
        major, minor = 0, 0
    # Declared: >=0.115,<0.116 — yield-dependency teardown changed in 0.118+
    supported = major == 0 and minor == 115
    return {
        "fastapi_version": ver,
        "supported_range": ">=0.115.0,<0.116",
        "supported": supported,
        "note_vi": (
            "FastAPI phải nằm trong khoảng đã pin để bảo đảm HTTP 503 sau lỗi outbox."
            if not supported
            else "FastAPI trong khoảng hỗ trợ."
        ),
    }
