"""P00-HF + P01 schema: idempotency, must_change_password, biometric tables

Revision ID: 20261102_0001
Revises:
Create Date: 2026-11-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261102_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" in tables:
        cols = {c["name"] for c in inspector.get_columns("users")}
        if "must_change_password" not in cols:
            with op.batch_alter_table("users") as batch:
                batch.add_column(
                    sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false())
                )

    if "raw_observations" in tables:
        cols = {c["name"] for c in inspector.get_columns("raw_observations")}
        if "idempotency_key" not in cols:
            with op.batch_alter_table("raw_observations") as batch:
                batch.add_column(
                    sa.Column("idempotency_key", sa.String(length=128), nullable=False, server_default="")
                )
            # Unique index — empty keys only acceptable for legacy rows during upgrade
            try:
                op.create_index(
                    "uq_raw_observation_idempotency",
                    "raw_observations",
                    ["idempotency_key"],
                    unique=True,
                )
            except Exception:
                pass

    if "biometric_enrollments" not in tables:
        op.create_table(
            "biometric_enrollments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
            sa.Column("authorization_ref", sa.String(255), server_default=""),
            sa.Column("authorization_ack_vi", sa.Text(), server_default=""),
            sa.Column("enrolled_by", sa.String(128), server_default=""),
            sa.Column("model_id", sa.String(128), server_default=""),
            sa.Column("model_hash", sa.String(128), server_default=""),
            sa.Column("template_version", sa.Integer(), server_default="1"),
            sa.Column("status", sa.String(64), server_default="ACTIVE"),
            sa.Column("sample_count", sa.Integer(), server_default="0"),
            sa.Column("quality_summary_json", sa.Text(), server_default="{}"),
            sa.Column("source", sa.String(64), server_default="DEMO"),
            sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoke_reason", sa.Text(), server_default=""),
        )
        op.create_index("ix_biometric_enrollments_employee_id", "biometric_enrollments", ["employee_id"])

    if "face_templates" not in tables:
        op.create_table(
            "face_templates",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "enrollment_id",
                sa.Integer(),
                sa.ForeignKey("biometric_enrollments.id"),
                nullable=False,
            ),
            sa.Column("encrypted_embedding", sa.LargeBinary(), nullable=False),
            sa.Column("nonce", sa.LargeBinary(), nullable=False),
            sa.Column("key_version", sa.Integer(), server_default="1"),
            sa.Column("vector_version", sa.String(64), server_default="sface-2021dec"),
            sa.Column("quality_score", sa.Float(), server_default="0"),
            sa.Column("quality_metadata", sa.Text(), server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("active", sa.Boolean(), server_default=sa.true()),
        )


def downgrade() -> None:
    # Non-destructive preference: do not drop biometric tables automatically in production.
    pass
