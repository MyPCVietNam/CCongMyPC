#!/usr/bin/env python3
"""Isolated reproduction, not a MyPC application integration test.

Shows that SQLAlchemy SQLite DateTime(timezone=True) can deserialize to a
naive datetime which cannot be compared with datetime.now(timezone.utc).
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, Integer, MetaData, Table, create_engine, insert, select

engine = create_engine("sqlite+pysqlite:///:memory:")
record = Table(
    "approval", MetaData(),
    Column("id", Integer, primary_key=True),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)
record.create(engine)
with engine.begin() as conn:
    conn.execute(insert(record).values(expires_at=datetime.now(timezone.utc) + timedelta(hours=2)))
    restored = conn.execute(select(record.c.expires_at)).scalar_one()
    print("deserialized_utc_tzinfo:", restored.tzinfo)
    try:
        print("expired:", restored < datetime.now(timezone.utc))
    except TypeError as exc:
        print("REPRODUCED_ERROR:", type(exc).__name__, str(exc))
        print("REPRODUCTION_PASS: actual application integration still required")
    else:
        print("NOT_REPRODUCED: inspect SQLAlchemy version or custom type mapper")
