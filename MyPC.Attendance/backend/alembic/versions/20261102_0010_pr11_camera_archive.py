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
    with op.batch_alter_table("camera_devices") as batch:
        batch.add_column(
            sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )
        batch.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("username_hint", sa.String(length=128), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column(
                "connection_status",
                sa.String(length=64),
                nullable=False,
                server_default="UNKNOWN",
            )
        )
        batch.add_column(
            sa.Column("config_revision", sa.String(length=64), nullable=False, server_default="")
        )


def downgrade() -> None:
    with op.batch_alter_table("camera_devices") as batch:
        batch.drop_column("config_revision")
        batch.drop_column("connection_status")
        batch.drop_column("username_hint")
        batch.drop_column("archived_at")
        batch.drop_column("archived")
