"""Current metadata for migration comparison; frozen v1 stays unchanged."""

from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from nicheradar.repositories.schema_v1 import metadata as frozen_v1

metadata = sa.MetaData(naming_convention=frozen_v1.naming_convention)
for table in frozen_v1.sorted_tables:
    table.to_metadata(metadata)
requests = metadata.tables["provider_requests"]
credit_balances = metadata.tables["credit_balances"]
credit_balances.append_column(
    sa.Column("refresh_required", sa.Boolean, nullable=False, server_default=sa.true())
)
credit_balances.append_column(
    sa.Column("unit", sa.String(50), nullable=False, server_default="vidiq_credit")
)
credit_balances.append_column(
    sa.Column("confirmed_usage", sa.Numeric(18, 6), nullable=False, server_default="0")
)
credit_balances.append_column(sa.Column("retain_until", sa.DateTime(timezone=True)))
credit_balances.append_column(
    sa.Column(
        "source_observation_id",
        UUID(as_uuid=True),
        sa.ForeignKey("raw_observations.id", ondelete="CASCADE"),
    )
)
balance_reconciliations = sa.Table(
    "balance_reconciliations",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
    sa.Column("provider", sa.String(40), nullable=False),
    sa.Column("auth_scope", sa.String(120), nullable=False),
    sa.Column("unit", sa.String(50), nullable=False),
    sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
    sa.Column("kind", sa.String(30), nullable=False),
    sa.Column("balance_change", sa.Numeric(18, 6)),
    sa.Column("radar_consumption", sa.Numeric(18, 6)),
    sa.Column("unattributed_change", sa.Numeric(18, 6)),
    sa.Column(
        "source_observation_id",
        UUID(as_uuid=True),
        sa.ForeignKey("raw_observations.id", ondelete="CASCADE"),
    ),
    sa.Column(
        "previous_observation_id",
        UUID(as_uuid=True),
        sa.ForeignKey("raw_observations.id", ondelete="CASCADE"),
    ),
)
ranking_snapshots = sa.Table(
    "ranking_snapshots",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
    sa.Column(
        "profile_id", UUID(as_uuid=True), sa.ForeignKey("creator_profiles.id"), nullable=False
    ),
    sa.Column(
        "run_id", UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id"), nullable=False, unique=True
    ),
    sa.Column("sequence", sa.Integer, nullable=False),
    sa.Column("mode", sa.String(20), nullable=False),
    sa.Column("method_version", sa.String(80), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("retain_until", sa.DateTime(timezone=True)),
    sa.Column("expired_at", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("profile_id", "sequence", name="uq_ranking_sequence"),
)
ranking_entries = sa.Table(
    "ranking_entries",
    metadata,
    sa.Column(
        "snapshot_id",
        UUID(as_uuid=True),
        sa.ForeignKey("ranking_snapshots.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "opportunity_id", UUID(as_uuid=True), sa.ForeignKey("opportunities.id"), primary_key=True
    ),
    sa.Column(
        "evaluation_id", UUID(as_uuid=True), sa.ForeignKey("evaluation_versions.id"), nullable=False
    ),
    sa.Column("group_key", sa.String(64)),
    sa.Column("scope", JSONB),
    sa.Column("position", sa.Integer),
    sa.Column("review_state", sa.String(30), nullable=False),
    sa.Column("reason", sa.String(80), nullable=False),
    sa.CheckConstraint("position IS NULL OR position > 0", name="ranking_position"),
)
opportunity_scoring_configs = sa.Table(
    "opportunity_scoring_configs",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
    sa.Column(
        "opportunity_id", UUID(as_uuid=True), sa.ForeignKey("opportunities.id"), nullable=False
    ),
    sa.Column(
        "profile_id", UUID(as_uuid=True), sa.ForeignKey("creator_profiles.id"), nullable=False
    ),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("configuration", JSONB),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
    sa.Column("expired_at", sa.DateTime(timezone=True)),
    sa.UniqueConstraint(
        "opportunity_id", "profile_id", "version", name="uq_opportunity_scoring_version"
    ),
    sa.CheckConstraint("version > 0", name="scoring_config_version"),
)
opportunity_recipe_assignments = sa.Table(
    "opportunity_recipe_assignments",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
    sa.Column(
        "opportunity_id", UUID(as_uuid=True), sa.ForeignKey("opportunities.id"), nullable=False
    ),
    sa.Column(
        "profile_id", UUID(as_uuid=True), sa.ForeignKey("creator_profiles.id"), nullable=False
    ),
    sa.Column(
        "recipe_id", UUID(as_uuid=True), sa.ForeignKey("production_recipes.id"), nullable=False
    ),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint(
        "opportunity_id", "profile_id", "version", name="uq_opportunity_recipe_version"
    ),
    sa.CheckConstraint("version > 0", name="recipe_assignment_version"),
)
production_recipe_defaults = sa.Table(
    "production_recipe_defaults",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
    sa.Column(
        "profile_id", UUID(as_uuid=True), sa.ForeignKey("creator_profiles.id"), nullable=False
    ),
    sa.Column("format", sa.String(20), nullable=False),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("configuration", JSONB, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint(
        "profile_id", "format", "version", name="uq_production_recipe_default_version"
    ),
    sa.CheckConstraint("version > 0", name="recipe_default_version"),
    sa.CheckConstraint("format IN ('long', 'shorts')", name="recipe_default_format"),
)
channel_analyses = sa.Table(
    "channel_analyses",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
    sa.Column(
        "profile_id", UUID(as_uuid=True), sa.ForeignKey("creator_profiles.id"), nullable=False
    ),
    sa.Column(
        "run_id", UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id"), nullable=False, unique=True
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
advertising_benchmarks = sa.Table(
    "advertising_benchmarks",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
    sa.Column("niche_label", sa.String(120), nullable=False, unique=True),
    sa.Column("niche_description", sa.Text, nullable=False),
    sa.Column("format", sa.String(20), nullable=False),
    sa.Column("rate_low", sa.Numeric, nullable=False),
    sa.Column("rate_high", sa.Numeric, nullable=False),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("assumptions", sa.Text, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("format IN ('long', 'shorts')", name="advertising_benchmark_format"),
    sa.CheckConstraint("rate_low <= rate_high", name="advertising_benchmark_rate_order"),
)
topic_artifact_sources = sa.Table(
    "topic_artifact_sources",
    metadata,
    sa.Column(
        "artifact_id",
        UUID(as_uuid=True),
        sa.ForeignKey("topic_artifacts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "observation_id",
        UUID(as_uuid=True),
        sa.ForeignKey("raw_observations.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
discovery_cursors = sa.Table(
    "discovery_cursors",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
    sa.Column(
        "profile_id", UUID(as_uuid=True), sa.ForeignKey("creator_profiles.id"), nullable=False
    ),
    sa.Column("family_id", UUID(as_uuid=True), sa.ForeignKey("seed_families.id"), nullable=False),
    sa.Column("opportunity_id", UUID(as_uuid=True), sa.ForeignKey("opportunities.id")),
    sa.Column("mode", sa.String(20), nullable=False),
    sa.Column("work_key", sa.String(120), nullable=False),
    sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
    sa.Column("completed_at", sa.DateTime(timezone=True)),
    sa.Column("pending_job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id")),
    sa.UniqueConstraint("profile_id", "mode", "work_key", name="uq_discovery_cursor_scope"),
    sa.CheckConstraint("mode IN ('synthetic', 'live')", name="discovery_mode"),
)
sa.Index(
    "uq_provider_requests_unresolved",
    requests.c.provider,
    requests.c.auth_scope,
    requests.c.cache_key,
    unique=True,
    postgresql_where=sa.text("state IN ('prepared', 'sent', 'unknown_charge')"),
)
market_intel_schedule = sa.Table(
    "market_intel_schedule",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
    sa.Column("schedule_key", sa.String(100), nullable=False, unique=True),
    sa.Column("paused", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Column("interval_seconds", sa.Integer, nullable=False),
    sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("configuration", JSONB, nullable=False),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.CheckConstraint("interval_seconds > 0", name="market_schedule_interval"),
)
market_scrape_runs = sa.Table(
    "market_scrape_runs",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
    sa.Column("run_key", sa.String(100), nullable=False, unique=True),
    sa.Column("analysis_run_id", UUID(as_uuid=True), sa.ForeignKey("analysis_runs.id")),
    sa.Column("status", sa.String(20), nullable=False),
    sa.Column("stage", sa.String(30), nullable=False),
    sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    sa.Column("lease_owner", sa.String(120)),
    sa.Column("lease_until", sa.DateTime(timezone=True)),
    sa.Column("checkpoints", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("error_code", sa.String(100)),
    sa.Column("stats", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("started_at", sa.DateTime(timezone=True)),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "status IN ('queued', 'running', 'succeeded', 'partial', 'failed', 'blocked')",
        name="market_run_status",
    ),
)
marketplace_listings = sa.Table(
    "marketplace_listings",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
    sa.Column("source", sa.String(40), nullable=False),
    sa.Column("external_id", sa.String(80), nullable=False),
    sa.Column("url", sa.Text, nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("category", sa.String(120)),
    sa.Column("status", sa.String(20), nullable=False, server_default="active"),
    sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
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
    sa.Column("detail_fetched_at", sa.DateTime(timezone=True)),
    sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("source", "external_id"),
    sa.CheckConstraint("status IN ('active', 'disappeared')", name="listing_status"),
    sa.Index("ix_marketplace_listings_status", "status"),
    sa.Index("ix_marketplace_listings_retain_until", "retain_until"),
)
listing_observations = sa.Table(
    "listing_observations",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
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
    sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("listing_id", "observed_on"),
    sa.CheckConstraint("origin = 'seller_declared'", name="observation_origin"),
)
listing_classifications = sa.Table(
    "listing_classifications",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
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
    sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("listing_id", "prompt_version"),
    sa.CheckConstraint("format IN ('long', 'shorts', 'unknown')", name="classification_format"),
    sa.CheckConstraint("source IN ('llm', 'synthetic_category_map')", name="classification_source"),
)
listing_verifications = sa.Table(
    "listing_verifications",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
    sa.Column(
        "listing_id",
        UUID(as_uuid=True),
        sa.ForeignKey("marketplace_listings.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("youtube_channel_id", sa.String(40)),
    sa.Column("real_subscribers", sa.BigInteger),
    sa.Column("status", sa.String(20), nullable=False),
    sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "status IN ('verified', 'mismatch', 'not_found', 'unverifiable')",
        name="verification_status",
    ),
    sa.Index("ix_listing_verifications_listing_id", "listing_id"),
)
niche_automation_priors = sa.Table(
    "niche_automation_priors",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
    sa.Column("niche_label", sa.String(120), nullable=False, unique=True),
    sa.Column("traits", JSONB, nullable=False),
    sa.Column("prompt_version", sa.String(40), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
market_niche_snapshots = sa.Table(
    "market_niche_snapshots",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
    sa.Column("snapshot_date", sa.Date, nullable=False),
    sa.Column("niche_label", sa.String(140), nullable=False),
    sa.Column("format", sa.String(10), nullable=False),
    sa.Column("stats", JSONB, nullable=False),
    sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("snapshot_date", "niche_label", "format"),
)
market_niche_decisions = sa.Table(
    "market_niche_decisions",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
    sa.Column("niche_label", sa.String(140), nullable=False),
    sa.Column("format", sa.String(10), nullable=False),
    sa.Column("decision", sa.String(20), nullable=False),
    sa.Column("note", sa.Text),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("decision IN ('nuevo', 'tentativo', 'descartado')", name="decision_value"),
    sa.Index("ix_market_niche_decisions_lookup", "niche_label", "format", "created_at"),
)
