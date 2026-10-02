"""Retained ranking snapshots, without copying scores or evidence text."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ranking_snapshots",
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
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("method_version", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retain_until", sa.DateTime(timezone=True)),
        sa.Column("expired_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("profile_id", "sequence", name="uq_ranking_sequence"),
    )
    op.create_table(
        "ranking_entries",
        sa.Column(
            "snapshot_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ranking_snapshots.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "opportunity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("opportunities.id"),
            primary_key=True,
        ),
        sa.Column(
            "evaluation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("evaluation_versions.id"),
            nullable=False,
        ),
        sa.Column("group_key", sa.String(64)),
        sa.Column("scope", JSONB),
        sa.Column("position", sa.Integer),
        sa.Column("review_state", sa.String(30), nullable=False),
        sa.Column("reason", sa.String(80), nullable=False),
        sa.CheckConstraint("position IS NULL OR position > 0", name="ranking_position"),
    )


def downgrade() -> None:
    op.drop_table("ranking_entries")
    op.drop_table("ranking_snapshots")
