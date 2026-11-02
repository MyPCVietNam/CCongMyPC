"""PR7: pilot evidence records + AB trust class + approval evidence_id.

Revision ID: 20261102_0007
Revises: 20261102_0006
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261102_0007"
down_revision: Union[str, None] = "20261102_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pilot_evidence_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("evidence_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("evidence_class", sa.String(length=32), nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("config_revision", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("provenance", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("decoded_w", sa.Integer(), nullable=True),
        sa.Column("decoded_h", sa.Integer(), nullable=True),
        sa.Column("fps_measured", sa.Float(), nullable=True),
        sa.Column("model_hash_pin", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("gallery_revision_pin", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("threshold_id_pin", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("windows_host", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("labeled_known", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("labeled_unknown", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("frame_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("ab_run_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("operator", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("note_vi", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["camera_id"], ["camera_devices.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evidence_id"),
    )
    op.create_index("ix_pilot_evidence_records_camera_id", "pilot_evidence_records", ["camera_id"])

    with op.batch_alter_table("ab_evaluation_runs") as batch:
        batch.add_column(
            sa.Column("evidence_class", sa.String(32), nullable=False, server_default="UNTRUSTED_IMPORT")
        )
        batch.add_column(sa.Column("config_revision", sa.String(64), nullable=False, server_default=""))
        batch.add_column(sa.Column("model_hash_pin", sa.String(128), nullable=False, server_default=""))
        batch.add_column(
            sa.Column("gallery_revision_pin", sa.String(128), nullable=False, server_default="")
        )
        batch.add_column(sa.Column("threshold_id_pin", sa.String(128), nullable=False, server_default=""))

    with op.batch_alter_table("pilot_approval_records") as batch:
        batch.add_column(sa.Column("evidence_id", sa.String(64), nullable=False, server_default=""))

    # Existing client-import AB rows stay non-promotable
    conn = op.get_bind()
    try:
        conn.execute(
            sa.text(
                "UPDATE ab_evaluation_runs SET evidence_class='UNTRUSTED_IMPORT', "
                "can_auto_enable=0, approval_status='REJECTED' "
                "WHERE evidence_class IS NULL OR evidence_class='' OR can_auto_enable=1"
            )
        )
    except Exception:
        pass


def downgrade() -> None:
    with op.batch_alter_table("pilot_approval_records") as batch:
        batch.drop_column("evidence_id")
    with op.batch_alter_table("ab_evaluation_runs") as batch:
        batch.drop_column("threshold_id_pin")
        batch.drop_column("gallery_revision_pin")
        batch.drop_column("model_hash_pin")
        batch.drop_column("config_revision")
        batch.drop_column("evidence_class")
    op.drop_index("ix_pilot_evidence_records_camera_id", table_name="pilot_evidence_records")
    op.drop_table("pilot_evidence_records")
