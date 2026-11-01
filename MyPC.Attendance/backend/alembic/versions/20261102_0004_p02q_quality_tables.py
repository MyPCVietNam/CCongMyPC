"""P02Q: stream profiles, quality settings, A/B evaluation runs (no biometric blobs).

Revision ID: 20261102_0004
Revises: 20261102_0003
Create Date: 2026-11-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261102_0004"
down_revision: Union[str, None] = "20261102_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "camera_stream_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("camera_id", sa.Integer(), sa.ForeignKey("camera_devices.id"), nullable=False),
        sa.Column("profile", sa.String(32), nullable=False, server_default="MAIN"),
        sa.Column("config_revision", sa.String(64), nullable=False, server_default=""),
        sa.Column("vendor_max_w", sa.Integer(), nullable=True),
        sa.Column("vendor_max_h", sa.Integer(), nullable=True),
        sa.Column("decoded_w", sa.Integer(), nullable=True),
        sa.Column("decoded_h", sa.Integer(), nullable=True),
        sa.Column("codec", sa.String(64), nullable=False, server_default=""),
        sa.Column("fps_measured", sa.Float(), nullable=True),
        sa.Column("health_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("camera_id", "profile", name="uq_camera_stream_profile"),
    )
    op.create_table(
        "camera_quality_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("camera_id", sa.Integer(), sa.ForeignKey("camera_devices.id"), nullable=False, unique=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("requested_mode", sa.String(32), nullable=False, server_default="AUTO"),
        sa.Column("effective_mode", sa.String(32), nullable=False, server_default="AUTO_TEST_ONLY"),
        sa.Column("model_hash_pin", sa.String(128), nullable=False, server_default=""),
        sa.Column("gallery_revision_pin", sa.String(128), nullable=False, server_default=""),
        sa.Column("threshold_id_pin", sa.String(128), nullable=False, server_default=""),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validated_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("reverted_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "ab_evaluation_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("camera_id", sa.Integer(), sa.ForeignKey("camera_devices.id"), nullable=True),
        sa.Column("run_id", sa.String(64), nullable=False, unique=True),
        sa.Column("source_mix", sa.String(64), nullable=False, server_default=""),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("blockers_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("can_auto_enable", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("approval_status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("approved_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note_vi", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("ab_evaluation_runs")
    op.drop_table("camera_quality_settings")
    op.drop_table("camera_stream_profiles")
