"""P02R: camera lab runs + face pilot case events + evidence lab_run_id.

Revision ID: 20261102_0008
Revises: 20261102_0007
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261102_0008"
down_revision: Union[str, None] = "20261102_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "camera_lab_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("nonce", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="CREATED"),
        sa.Column("profile", sa.String(32), nullable=False, server_default="MAIN"),
        sa.Column("config_revision", sa.String(64), nullable=False, server_default=""),
        sa.Column("provenance", sa.String(32), nullable=False, server_default=""),
        sa.Column("source_generation", sa.String(64), nullable=False, server_default=""),
        sa.Column("model_hash_pin", sa.String(128), nullable=False, server_default=""),
        sa.Column("gallery_revision_pin", sa.String(128), nullable=False, server_default=""),
        sa.Column("threshold_id_pin", sa.String(128), nullable=False, server_default=""),
        sa.Column("decoded_w", sa.Integer(), nullable=True),
        sa.Column("decoded_h", sa.Integer(), nullable=True),
        sa.Column("fps_measured", sa.Float(), nullable=True),
        sa.Column("frame_age_ms", sa.Float(), nullable=True),
        sa.Column("frame_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("reconnect_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decode_errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("owner_challenge", sa.String(64), nullable=False, server_default=""),
        sa.Column("owner_reviewed_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("owner_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("operator", sa.String(128), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("note_vi", sa.Text(), nullable=False, server_default=""),
        sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["camera_id"], ["camera_devices.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
        sa.UniqueConstraint("nonce"),
    )
    op.create_index("ix_camera_lab_runs_camera_id", "camera_lab_runs", ["camera_id"])

    op.create_table(
        "face_pilot_case_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("lab_run_id", sa.String(64), nullable=False),
        sa.Column("camera_id", sa.Integer(), nullable=False),
        sa.Column("frame_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("config_revision", sa.String(64), nullable=False, server_default=""),
        sa.Column("truth_label", sa.String(64), nullable=False),
        sa.Column("pred_label", sa.String(64), nullable=False, server_default=""),
        sa.Column("outcome", sa.String(32), nullable=False, server_default=""),
        sa.Column("similarity", sa.Float(), nullable=True),
        sa.Column("condition", sa.String(32), nullable=False, server_default="DAY"),
        sa.Column("native_face_width_px", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("model_hash_pin", sa.String(128), nullable=False, server_default=""),
        sa.Column("gallery_revision_pin", sa.String(128), nullable=False, server_default=""),
        sa.Column("threshold_id_pin", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note_vi", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id"),
    )
    op.create_index("ix_face_pilot_case_events_lab_run_id", "face_pilot_case_events", ["lab_run_id"])

    with op.batch_alter_table("pilot_evidence_records") as batch:
        batch.add_column(sa.Column("lab_run_id", sa.String(64), nullable=False, server_default=""))
    op.create_index("ix_pilot_evidence_records_lab_run_id", "pilot_evidence_records", ["lab_run_id"])


def downgrade() -> None:
    op.drop_index("ix_pilot_evidence_records_lab_run_id", table_name="pilot_evidence_records")
    with op.batch_alter_table("pilot_evidence_records") as batch:
        batch.drop_column("lab_run_id")
    op.drop_index("ix_face_pilot_case_events_lab_run_id", table_name="face_pilot_case_events")
    op.drop_table("face_pilot_case_events")
    op.drop_index("ix_camera_lab_runs_camera_id", table_name="camera_lab_runs")
    op.drop_table("camera_lab_runs")
