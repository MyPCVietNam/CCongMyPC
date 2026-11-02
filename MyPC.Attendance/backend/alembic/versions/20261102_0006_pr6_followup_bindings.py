"""PR6 follow-up: enrollment camera binding + revert unsafe AUTO_VALIDATED.

Revision ID: 20261102_0006
Revises: 20261102_0005
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261102_0006"
down_revision: Union[str, None] = "20261102_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("enrollment_sessions") as batch:
        batch.add_column(sa.Column("camera_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("bound_profile", sa.String(32), nullable=False, server_default=""))
        batch.add_column(
            sa.Column("bound_config_revision", sa.String(64), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column("camera_lab_approval_id", sa.String(64), nullable=False, server_default="")
        )
    # Idempotent safety: demote any AUTO_VALIDATED without evidence path to AUTO_TEST_ONLY
    conn = op.get_bind()
    try:
        conn.execute(
            sa.text(
                "UPDATE camera_quality_settings SET effective_mode='AUTO_TEST_ONLY', "
                "reverted_reason='PR6_MIGRATION_UNSIGNED_AUTO_VALIDATED' "
                "WHERE effective_mode='AUTO_VALIDATED'"
            )
        )
    except Exception:
        # Table may not exist on partial DBs; create_all/migrate order handles later
        pass


def downgrade() -> None:
    with op.batch_alter_table("enrollment_sessions") as batch:
        batch.drop_column("camera_lab_approval_id")
        batch.drop_column("bound_config_revision")
        batch.drop_column("bound_profile")
        batch.drop_column("camera_id")
