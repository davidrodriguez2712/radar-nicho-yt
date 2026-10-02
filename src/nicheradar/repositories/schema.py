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
