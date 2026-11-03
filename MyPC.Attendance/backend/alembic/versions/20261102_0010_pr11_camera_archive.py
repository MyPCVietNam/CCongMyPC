"""PR11-HF: camera archive + username hint + connection status.

Revision ID: 20261102_0010
Revises: 20261102_0009
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261102_0010"
down_revision: Union[str, None] = "20261102_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "camera_devices" not in inspector.get_table_names():
        raise RuntimeError("Migration 0010 requires table 'camera_devices'")
    cols = {c["name"] for c in inspector.get_columns("camera_devices")}
    to_add = [
        ("archived", sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("0"))),
        ("archived_at", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)),
        (
            "username_hint",
            sa.Column("username_hint", sa.String(length=128), nullable=False, server_default=""),
        ),
        (
            "connection_status",
            sa.Column(
                "connection_status",
                sa.String(length=64),
                nullable=False,
                server_default="UNKNOWN",
            ),
        ),
        (
            "config_revision",
            sa.Column("config_revision", sa.String(length=64), nullable=False, server_default=""),
        ),
    ]
    missing = [(name, col) for name, col in to_add if name not in cols]
    if missing:
        with op.batch_alter_table("camera_devices") as batch:
            for _, col in missing:
                batch.add_column(col)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "camera_devices" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("camera_devices")}
    with op.batch_alter_table("camera_devices") as batch:
        for col in (
            "config_revision",
            "connection_status",
            "username_hint",
            "archived_at",
            "archived",
        ):
            if col in cols:
                batch.drop_column(col)
