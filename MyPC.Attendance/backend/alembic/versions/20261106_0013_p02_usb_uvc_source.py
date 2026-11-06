"""P02-USB: camera source_type + USB stable identity columns.

Revision ID: 20261106_0013
Revises: 20261103_0012
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261106_0013"
down_revision: Union[str, None] = "20261103_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "camera_devices" not in tables:
        raise RuntimeError("Migration 0013 requires table 'camera_devices'")

    cam_cols = {c["name"] for c in inspector.get_columns("camera_devices")}
    with op.batch_alter_table("camera_devices") as batch:
        if "source_type" not in cam_cols:
            batch.add_column(
                sa.Column("source_type", sa.String(length=32), nullable=False, server_default="RTSP")
            )
        if "usb_stable_id" not in cam_cols:
            batch.add_column(
                sa.Column("usb_stable_id", sa.String(length=128), nullable=False, server_default="")
            )
        if "usb_friendly_name" not in cam_cols:
            batch.add_column(
                sa.Column("usb_friendly_name", sa.String(length=128), nullable=False, server_default="")
            )
        if "usb_index_hint" not in cam_cols:
            batch.add_column(sa.Column("usb_index_hint", sa.Integer(), nullable=True))

    if "camera_live_bindings" in tables:
        bcols = {c["name"] for c in inspector.get_columns("camera_live_bindings")}
        if "usb_stable_id" not in bcols:
            with op.batch_alter_table("camera_live_bindings") as batch:
                batch.add_column(
                    sa.Column(
                        "usb_stable_id", sa.String(length=128), nullable=False, server_default=""
                    )
                )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "camera_live_bindings" in tables:
        bcols = {c["name"] for c in inspector.get_columns("camera_live_bindings")}
        if "usb_stable_id" in bcols:
            with op.batch_alter_table("camera_live_bindings") as batch:
                batch.drop_column("usb_stable_id")
    if "camera_devices" in tables:
        cam_cols = {c["name"] for c in inspector.get_columns("camera_devices")}
        with op.batch_alter_table("camera_devices") as batch:
            for col in ("usb_index_hint", "usb_friendly_name", "usb_stable_id", "source_type"):
                if col in cam_cols:
                    batch.drop_column(col)
