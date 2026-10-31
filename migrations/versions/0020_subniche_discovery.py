"""Descubrimiento de subnichos desde YouTube (additive)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def _ts(name: str, nullable: bool = True) -> sa.Column[object]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "niche_hypotheses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(60), nullable=False, unique=True),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("family", sa.String(40), nullable=False),
        sa.Column("parent_niche_slug", sa.String(60)),
        sa.Column("queries", JSONB, nullable=False),
        sa.Column("language", sa.String(5), nullable=False, server_default="en"),
        sa.Column("format", sa.String(10), nullable=False, server_default="long"),
        sa.Column("origin", sa.String(12), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="proposed"),
        sa.Column("finalist", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("source_input", sa.Text),
        _ts("created_at", nullable=False),
        _ts("approved_at"),
        _ts("last_measured_at"),
        sa.CheckConstraint(
            "origin IN ('manual', 'catalog', 'marketplace', 'lead')", name="hypothesis_origin"
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'active', 'paused', 'archived')", name="hypothesis_status"
        ),
    )
    op.create_table(
        "hypothesis_seed_channels",
        sa.Column(
            "hypothesis_id",
            UUID(as_uuid=True),
            sa.ForeignKey("niche_hypotheses.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("channel_id", sa.String(40), primary_key=True),
        _ts("added_at", nullable=False),
    )
    op.create_table(
        "discovery_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "analysis_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("analysis_runs.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(10), nullable=False),
        _ts("started_at", nullable=False),
        _ts("finished_at"),
        sa.Column("stats", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint(
            "status IN ('running', 'partial', 'complete', 'failed')", name="discovery_run_status"
        ),
    )
    op.create_table(
        "discovery_channel_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("discovery_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel_id", sa.String(40), nullable=False),
        _ts("fetched_at", nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("country", sa.String(2)),
        _ts("channel_created_at"),
        sa.Column("subscribers", sa.BigInteger),
        sa.Column("total_views", sa.BigInteger),
        sa.Column("video_count", sa.BigInteger),
        sa.Column("recent_videos", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        _ts("retain_until", nullable=False),
    )
    op.create_index(
        "ix_discovery_channel_snapshots_channel_id", "discovery_channel_snapshots", ["channel_id"]
    )
    op.create_table(
        "hypothesis_channel_hits",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "hypothesis_id",
            UUID(as_uuid=True),
            sa.ForeignKey("niche_hypotheses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("discovery_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel_id", sa.String(40), nullable=False),
        sa.Column("source", sa.String(6), nullable=False),
        sa.Column("rank", sa.Integer),
        sa.Column("subscribers", sa.BigInteger),
        sa.Column("monthly_long_views", sa.BigInteger, nullable=False),
        sa.Column("income_low", sa.Numeric(14, 2)),
        sa.Column("income_high", sa.Numeric(14, 2)),
        sa.Column("shorts_share", sa.Numeric(5, 4)),
        sa.Column("outlier_ratio_max", sa.Numeric(10, 2)),
        sa.Column("small_channel", sa.Boolean, nullable=False),
        sa.Column("traction", sa.Boolean, nullable=False),
        sa.Column("flags", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("excluded_reason", sa.String(30)),
        _ts("retain_until", nullable=False),
        sa.CheckConstraint("source IN ('search', 'seed')", name="hit_source"),
        sa.UniqueConstraint("hypothesis_id", "run_id", "channel_id", name="uq_hit_per_run"),
    )
    op.create_table(
        "hypothesis_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "hypothesis_id",
            UUID(as_uuid=True),
            sa.ForeignKey("niche_hypotheses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("discovery_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        _ts("measured_at", nullable=False),
        sa.Column("stable_channels", sa.Integer, nullable=False),
        sa.Column("traction_channels", sa.Integer, nullable=False),
        sa.Column("median_income_low", sa.Numeric(14, 2)),
        sa.Column("median_income_high", sa.Numeric(14, 2)),
        sa.Column("profile", JSONB, nullable=False),
        sa.UniqueConstraint("hypothesis_id", "run_id", name="uq_snapshot_per_run"),
    )


def downgrade() -> None:
    op.drop_table("hypothesis_snapshots")
    op.drop_table("hypothesis_channel_hits")
    op.drop_index(
        "ix_discovery_channel_snapshots_channel_id", table_name="discovery_channel_snapshots"
    )
    op.drop_table("discovery_channel_snapshots")
    op.drop_table("discovery_runs")
    op.drop_table("hypothesis_seed_channels")
    op.drop_table("niche_hypotheses")
