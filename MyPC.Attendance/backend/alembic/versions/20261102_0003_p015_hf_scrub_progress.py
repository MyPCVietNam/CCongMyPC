"""P01.5-HF: scrub plaintext face_embeddings from enrollment_sessions.progress_json

Revision ID: 20261102_0003
Revises: 20261102_0002
Create Date: 2026-11-02

NOTE ON DELETION: This migration removes sensitive JSON keys from the column value.
It does NOT securely wipe SQLite WAL pages, vacuum-free free lists, filesystem snapshots,
or off-site backups. Operators must rotate encryption keys if real embeddings were ever
written, review backups, and treat historical copies as potentially sensitive until
disposed under retention policy. Do not claim secure deletion unless independently verified.
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261102_0003"
down_revision: Union[str, None] = "20261102_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FORBIDDEN = {
    "face_embeddings",
    "embeddings",
    "embedding",
    "vectors",
    "vector",
    "raw_embedding",
    "probe",
    "password",
    "camera_password",
    "rtsp_url",
    "secret",
}


def _scrub(obj: dict) -> dict:
    out = {}
    for k, v in obj.items():
        if k in FORBIDDEN:
            continue
        out[k] = v
    # Keep only non-sensitive known fields when possible
    allowed = {
        "completed_slots",
        "samples",
        "frame_hashes",
        "announcements",
        "quality_scores",
        "capture_origin",
        "algorithm_backend",
        "testing_mode",
        "model_id",
        "model_hash",
    }
    return {k: out[k] for k in allowed if k in out}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "enrollment_sessions" not in inspector.get_table_names():
        return
    rows = bind.execute(sa.text("SELECT id, progress_json FROM enrollment_sessions")).fetchall()
    for rid, raw in rows:
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        if not isinstance(data, dict):
            continue
        if not any(k in data for k in FORBIDDEN):
            # Still normalize
            scrubbed = _scrub(data)
        else:
            scrubbed = _scrub(data)
        new_raw = json.dumps(scrubbed, ensure_ascii=False)
        if new_raw != raw:
            bind.execute(
                sa.text("UPDATE enrollment_sessions SET progress_json = :p WHERE id = :id"),
                {"p": new_raw, "id": rid},
            )


def downgrade() -> None:
    # Irreversible scrub — cannot restore wiped embeddings (by design).
    pass
