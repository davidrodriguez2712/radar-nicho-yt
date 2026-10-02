"""Channel competitive analysis: saved, immutable per-run snapshots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_analyses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id", UUID(as_uuid=True), sa.ForeignKey("creator_profiles.id"), nullable=False
        ),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("analysis_runs.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("channel_input", sa.Text, nullable=False),
        sa.Column("channel_external_id", sa.String(80)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("configuration", JSONB, nullable=False),
        sa.Column("snapshot", JSONB),
        sa.Column("consumption", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expired_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('completed', 'partial', 'failed')", name="channel_analysis_status"
        ),
    )


def downgrade() -> None:
    op.drop_table("channel_analyses")
