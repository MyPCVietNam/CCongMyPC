"""SQLAlchemy engine/session with SQLite WAL pragmas."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def _configure_sqlite(dbapi_conn, connection_record) -> None:  # noqa: ARG001
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def create_db_engine(database_url: str) -> Engine:
    connect_args: dict = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # ensure parent dir
        if database_url.startswith("sqlite:///"):
            path = Path(database_url.replace("sqlite:///", "", 1))
            path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, connect_args=connect_args, future=True)
    if database_url.startswith("sqlite"):
        event.listen(engine, "connect", _configure_sqlite)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def session_scope(factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_integrity(engine: Engine) -> str:
    with engine.connect() as conn:
        row = conn.execute(text("PRAGMA integrity_check")).fetchone()
        return str(row[0]) if row else "unknown"
