"""Commit-proven secret FS outbox + camera secret_generation.

Revision ID: 20261103_0011
Revises: 20261102_0010
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261103_0011"
down_revision: Union[str, None] = "20261102_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("camera_devices") as batch:
        batch.add_column(
            sa.Column(
                "secret_generation",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )

    op.create_table(
        "secret_fs_outbox",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=True),
        sa.Column("op", sa.String(length=32), nullable=False),
        sa.Column("staged_ref", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("live_ref", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("delete_ref", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("8")),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("public_id", name="uq_secret_fs_outbox_public_id"),
    )
    op.create_index("ix_secret_fs_outbox_status", "secret_fs_outbox", ["status"])
    op.create_index(
        "ix_secret_fs_outbox_camera_gen", "secret_fs_outbox", ["camera_id", "generation"]
    )


def downgrade() -> None:
    op.drop_index("ix_secret_fs_outbox_camera_gen", table_name="secret_fs_outbox")
    op.drop_index("ix_secret_fs_outbox_status", table_name="secret_fs_outbox")
    op.drop_table("secret_fs_outbox")
    with op.batch_alter_table("camera_devices") as batch:
        batch.drop_column("secret_generation")
