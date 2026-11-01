"""P01.5 auto enrollment sessions and sample tables

Revision ID: 20261102_0002
Revises: 20261102_0001
Create Date: 2026-11-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261102_0002"
down_revision: Union[str, None] = "20261102_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "face_templates" in tables:
        cols = {c["name"] for c in inspector.get_columns("face_templates")}
        if "pose_slot" not in cols:
            with op.batch_alter_table("face_templates") as batch:
                batch.add_column(sa.Column("pose_slot", sa.String(32), server_default=""))

    if "enrollment_sessions" not in tables:
        op.create_table(
            "enrollment_sessions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("public_id", sa.String(64), nullable=False),
            sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
            sa.Column(
                "enrollment_id",
                sa.Integer(),
                sa.ForeignKey("biometric_enrollments.id"),
                nullable=False,
            ),
            sa.Column("operator", sa.String(128), server_default=""),
            sa.Column("status", sa.String(64), server_default="WAITING_FOR_PERSON"),
            sa.Column("current_step", sa.String(64), server_default="FACE_FRONT"),
            sa.Column("ui_state", sa.String(64), server_default="WAITING_FOR_PERSON"),
            sa.Column("guidance_vi", sa.Text(), server_default=""),
            sa.Column("progress_json", sa.Text(), server_default="{}"),
            sa.Column("source", sa.String(64), server_default="DEMO"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_enrollment_sessions_public_id", "enrollment_sessions", ["public_id"], unique=True)
        op.create_index("ix_enrollment_sessions_employee_id", "enrollment_sessions", ["employee_id"])

    if "enrollment_samples" not in tables:
        op.create_table(
            "enrollment_samples",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "session_id",
                sa.Integer(),
                sa.ForeignKey("enrollment_sessions.id"),
                nullable=False,
            ),
            sa.Column("sample_uid", sa.String(64), nullable=False),
            sa.Column("slot", sa.String(32), nullable=False),
            sa.Column("kind", sa.String(16), server_default="FACE"),
            sa.Column("quality_score", sa.Float(), server_default="0"),
            sa.Column("quality_json", sa.Text(), server_default="{}"),
            sa.Column("native_width", sa.Integer(), server_default="0"),
            sa.Column("native_height", sa.Integer(), server_default="0"),
            sa.Column("person_height_px", sa.Integer(), server_default="0"),
            sa.Column("model_id", sa.String(128), server_default=""),
            sa.Column("model_hash", sa.String(128), server_default=""),
            sa.Column("frame_hash", sa.String(64), server_default=""),
            sa.Column("encrypted_image", sa.LargeBinary(), nullable=True),
            sa.Column("image_nonce", sa.LargeBinary(), nullable=True),
            sa.Column("encrypted_embedding", sa.LargeBinary(), nullable=True),
            sa.Column("embedding_nonce", sa.LargeBinary(), nullable=True),
            sa.Column("accepted", sa.Boolean(), server_default=sa.true()),
            sa.Column("replaced", sa.Boolean(), server_default=sa.false()),
            sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_enrollment_samples_session_id", "enrollment_samples", ["session_id"])
        op.create_index("ix_enrollment_samples_sample_uid", "enrollment_samples", ["sample_uid"], unique=True)


def downgrade() -> None:
    pass
