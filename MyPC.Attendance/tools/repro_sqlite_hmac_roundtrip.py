#!/usr/bin/env python3
"""Safe standalone SQLite/SQLAlchemy timestamp + HMAC round-trip illustration.

Does not import MyPC Attendance or use any project secrets or biometric data.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from sqlalchemy import Column, DateTime, Integer, MetaData, Table, create_engine, insert, select

key = b"LOCAL-DEMO-ONLY-NOT-A-REAL-SECRET"
engine = create_engine("sqlite+pysqlite:///:memory:")
tab = Table("demo", MetaData(), Column("id", Integer, primary_key=True), Column("expires", DateTime(timezone=True)))
tab.create(engine)
expiry = datetime.now(timezone.utc) + timedelta(hours=3)

def signed_text(ts: datetime) -> str:
    return json.dumps({"expires_at": ts.isoformat(), "kind": "CAMERA_LAB"}, sort_keys=True, separators=(",", ":"))

before = signed_text(expiry)
signature = hmac.new(key, before.encode("utf-8"), hashlib.sha256).hexdigest()
with engine.begin() as c:
    c.execute(insert(tab).values(expires=expiry))
with engine.connect() as c:
    restored = c.execute(select(tab.c.expires)).scalar_one()
after = signed_text(restored)
new_signature = hmac.new(key, after.encode("utf-8"), hashlib.sha256).hexdigest()
print("ORIGINAL_OFFSET:", expiry.utcoffset())
print("LOADED_TZINFO:", restored.tzinfo)
print("CANONICAL_TEXT_EQUAL:", before == after)
print("HMAC_VERIFIES_AFTER_LOAD:", hmac.compare_digest(signature, new_signature))
print("OBSERVED_RESULT: standalone SQLite representation changes; app integration test still required")
