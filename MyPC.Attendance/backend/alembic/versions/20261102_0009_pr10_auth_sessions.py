"""PR10-HF: user auth_epoch + durable auth_sessions.

Revision ID: 20261102_0009
Revises: 20261102_0008
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261102_0009"
down_revision: Union[str, None] = "20261102_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" in tables:
        cols = {c["name"] for c in inspector.get_columns("users")}
        if "auth_epoch" not in cols:
            with op.batch_alter_table("users") as batch:
                batch.add_column(
                    sa.Column("auth_epoch", sa.Integer(), nullable=False, server_default="1")
                )
    # Fresh installs stamp HEAD after create_all — this path is for upgrades
    # from 0008 where users already exists. If users is missing, fail loudly
    # rather than create a half-migrated schema (bootstrap_schema handles empty DBs).
    if "users" not in tables:
        raise RuntimeError(
            "Migration 0009 requires table 'users'. Empty databases must use "
            "fresh bootstrap (create_all + stamp HEAD), not incremental upgrade."
        )

    if "auth_sessions" not in tables:
        op.create_table(
            "auth_sessions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("sid", sa.String(64), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("auth_epoch", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("revoke_reason", sa.String(64), nullable=False, server_default=""),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("sid"),
        )
        op.create_index("ix_auth_sessions_sid", "auth_sessions", ["sid"])
        op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "auth_sessions" in tables:
        op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
        op.drop_index("ix_auth_sessions_sid", table_name="auth_sessions")
        op.drop_table("auth_sessions")
    if "users" in tables:
        cols = {c["name"] for c in inspector.get_columns("users")}
        if "auth_epoch" in cols:
            with op.batch_alter_table("users") as batch:
                batch.drop_column("auth_epoch")
