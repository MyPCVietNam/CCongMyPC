"""Camera lifecycle_id fence + outbox camera_lifecycle_id (C14 id-reuse).

Revision ID: 20261103_0012
Revises: 20261103_0011
"""

from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261103_0012"
down_revision: Union[str, None] = "20261103_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "camera_devices" not in tables:
        raise RuntimeError("Migration 0012 requires table 'camera_devices'")

    cam_cols = {c["name"] for c in inspector.get_columns("camera_devices")}
    if "lifecycle_id" not in cam_cols:
        with op.batch_alter_table("camera_devices") as batch:
            batch.add_column(
                sa.Column(
                    "lifecycle_id",
                    sa.String(length=64),
                    nullable=False,
                    server_default="",
                )
            )

    if "secret_fs_outbox" in tables:
        out_cols = {c["name"] for c in inspector.get_columns("secret_fs_outbox")}
        if "camera_lifecycle_id" not in out_cols:
            with op.batch_alter_table("secret_fs_outbox") as batch:
                batch.add_column(
                    sa.Column(
                        "camera_lifecycle_id",
                        sa.String(length=64),
                        nullable=False,
                        server_default="",
                    )
                )

    # Backfill immutable instance ids for existing cameras missing a lifecycle id
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id FROM camera_devices "
            "WHERE lifecycle_id IS NULL OR lifecycle_id = ''"
        )
    ).fetchall()
    for (cid,) in rows:
        lid = uuid.uuid4().hex
        conn.execute(
            sa.text("UPDATE camera_devices SET lifecycle_id = :lid WHERE id = :cid"),
            {"lid": lid, "cid": cid},
        )
        if "secret_fs_outbox" in tables:
            conn.execute(
                sa.text(
                    "UPDATE secret_fs_outbox SET camera_lifecycle_id = :lid "
                    "WHERE camera_id = :cid AND (camera_lifecycle_id = '' OR camera_lifecycle_id IS NULL)"
                ),
                {"lid": lid, "cid": cid},
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "secret_fs_outbox" in tables:
        cols = {c["name"] for c in inspector.get_columns("secret_fs_outbox")}
        if "camera_lifecycle_id" in cols:
            with op.batch_alter_table("secret_fs_outbox") as batch:
                batch.drop_column("camera_lifecycle_id")
    if "camera_devices" in tables:
        cols = {c["name"] for c in inspector.get_columns("camera_devices")}
        if "lifecycle_id" in cols:
            with op.batch_alter_table("camera_devices") as batch:
                batch.drop_column("lifecycle_id")
