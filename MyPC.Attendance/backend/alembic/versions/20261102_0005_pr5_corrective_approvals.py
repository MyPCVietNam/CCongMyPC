"""PR5 corrective: pilot approvals + live bindings persistence.

Revision ID: 20261102_0005
Revises: 20261102_0004
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261102_0005"
down_revision: Union[str, None] = "20261102_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pilot_approval_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("approval_id", sa.String(64), nullable=False, unique=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("camera_id", sa.Integer(), sa.ForeignKey("camera_devices.id"), nullable=True),
        sa.Column("model_hash_pin", sa.String(128), nullable=False, server_default=""),
        sa.Column("gallery_revision_pin", sa.String(128), nullable=False, server_default=""),
        sa.Column("threshold_id_pin", sa.String(128), nullable=False, server_default=""),
        sa.Column("ab_run_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("issued_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signature", sa.String(128), nullable=False, server_default=""),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("note_vi", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_table(
        "camera_live_bindings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("camera_id", sa.Integer(), sa.ForeignKey("camera_devices.id"), nullable=False, unique=True),
        sa.Column("scheme", sa.String(16), nullable=False, server_default="rtsp"),
        sa.Column("host", sa.String(255), nullable=False, server_default=""),
        sa.Column("port", sa.Integer(), nullable=False, server_default="554"),
        sa.Column("path", sa.String(255), nullable=False, server_default=""),
        sa.Column("profile", sa.String(32), nullable=False, server_default="MAIN"),
        sa.Column("resolved_ips_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("config_revision", sa.String(64), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("camera_live_bindings")
    op.drop_table("pilot_approval_records")
