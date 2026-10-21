"""Market intelligence: marketplace listings, scoring inputs and scraper state (additive)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def _tz(name: str, *, nullable: bool = True) -> sa.Column[object]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "market_intel_schedule",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("schedule_key", sa.String(100), nullable=False, unique=True),
        sa.Column("paused", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("interval_seconds", sa.Integer, nullable=False),
        _tz("next_due_at", nullable=False),
        sa.Column("configuration", JSONB, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("interval_seconds > 0", name="market_schedule_interval"),
    )
    op.create_table(
        "market_scrape_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("run_key", sa.String(100), nullable=False, unique=True),
        sa.Column("analysis_run_id", UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id")),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stage", sa.String(30), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("lease_owner", sa.String(120)),
        _tz("lease_until"),
        sa.Column("checkpoints", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_code", sa.String(100)),
        sa.Column("stats", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        _tz("started_at"),
        _tz("finished_at"),
        _tz("created_at", nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'partial', 'failed', 'blocked')",
            name="market_run_status",
        ),
    )
    op.create_table(
        "marketplace_listings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("external_id", sa.String(80), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("category", sa.String(120)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        _tz("first_seen_at", nullable=False),
        _tz("last_seen_at", nullable=False),
        sa.Column("consecutive_misses", sa.Integer, nullable=False, server_default="0"),
        sa.Column("price_usd", sa.Numeric(14, 2)),
        sa.Column("subscribers", sa.BigInteger),
        sa.Column("income_monthly_usd", sa.Numeric(14, 2)),
        sa.Column("expense_monthly_usd", sa.Numeric(14, 2)),
        sa.Column("description", sa.Text),
        sa.Column("monetization", sa.String(20)),
        sa.Column("content_type", sa.String(120)),
        sa.Column("published_text", sa.String(80)),
        sa.Column("youtube_channel_id", sa.String(40)),
        sa.Column("channel_url", sa.Text),
        _tz("detail_fetched_at"),
        _tz("retain_until", nullable=False),
        sa.UniqueConstraint("source", "external_id"),
        sa.CheckConstraint("status IN ('active', 'disappeared')", name="listing_status"),
    )
    op.create_index("ix_marketplace_listings_status", "marketplace_listings", ["status"])
    op.create_index(
        "ix_marketplace_listings_retain_until", "marketplace_listings", ["retain_until"]
    )
    op.create_table(
        "listing_observations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "listing_id",
            UUID(as_uuid=True),
            sa.ForeignKey("marketplace_listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("observed_on", sa.Date, nullable=False),
        sa.Column("price_usd", sa.Numeric(14, 2)),
        sa.Column("subscribers", sa.BigInteger),
        sa.Column("income_monthly_usd", sa.Numeric(14, 2)),
        sa.Column("expense_monthly_usd", sa.Numeric(14, 2)),
        sa.Column("category", sa.String(120)),
        sa.Column("origin", sa.String(30), nullable=False, server_default="seller_declared"),
        _tz("retain_until", nullable=False),
        _tz("created_at", nullable=False),
        sa.UniqueConstraint("listing_id", "observed_on"),
        sa.CheckConstraint("origin = 'seller_declared'", name="observation_origin"),
    )
    op.create_table(
        "listing_classifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "listing_id",
            UUID(as_uuid=True),
            sa.ForeignKey("marketplace_listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("niche_label", sa.String(120)),
        sa.Column("other_label", sa.String(80)),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("language", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("traits", JSONB, nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6)),
        _tz("retain_until", nullable=False),
        _tz("created_at", nullable=False),
        sa.UniqueConstraint("listing_id", "prompt_version"),
        sa.CheckConstraint("format IN ('long', 'shorts', 'unknown')", name="classification_format"),
        sa.CheckConstraint(
            "source IN ('llm', 'synthetic_category_map')", name="classification_source"
        ),
    )
    op.create_table(
        "listing_verifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "listing_id",
            UUID(as_uuid=True),
            sa.ForeignKey("marketplace_listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("youtube_channel_id", sa.String(40)),
        sa.Column("real_subscribers", sa.BigInteger),
        sa.Column("status", sa.String(20), nullable=False),
        _tz("checked_at", nullable=False),
        _tz("retain_until", nullable=False),
        sa.CheckConstraint(
            "status IN ('verified', 'mismatch', 'not_found', 'unverifiable')",
            name="verification_status",
        ),
    )
    op.create_index("ix_listing_verifications_listing_id", "listing_verifications", ["listing_id"])
    op.create_table(
        "niche_automation_priors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("niche_label", sa.String(120), nullable=False, unique=True),
        sa.Column("traits", JSONB, nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        _tz("created_at", nullable=False),
    )
    op.create_table(
        "market_niche_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("niche_label", sa.String(140), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("stats", JSONB, nullable=False),
        _tz("retain_until", nullable=False),
        sa.UniqueConstraint("snapshot_date", "niche_label", "format"),
    )
    op.create_table(
        "market_niche_decisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("niche_label", sa.String(140), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("note", sa.Text),
        _tz("created_at", nullable=False),
        sa.CheckConstraint(
            "decision IN ('nuevo', 'tentativo', 'descartado')", name="decision_value"
        ),
    )
    op.create_index(
        "ix_market_niche_decisions_lookup",
        "market_niche_decisions",
        ["niche_label", "format", "created_at"],
    )


def downgrade() -> None:
    for name in (
        "market_niche_decisions",
        "market_niche_snapshots",
        "niche_automation_priors",
        "listing_verifications",
        "listing_classifications",
        "listing_observations",
        "marketplace_listings",
        "market_scrape_runs",
        "market_intel_schedule",
    ):
        op.drop_table(name)
