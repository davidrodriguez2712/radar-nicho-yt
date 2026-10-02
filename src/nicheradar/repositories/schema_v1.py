"""Frozen schema snapshot for migration 0001. Future changes require a new revision.

Operational JSON fields contain versioned contracts; identity, money, time, linkage
and uniqueness remain relational. No active experiment entity exists in V1.
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

metadata = sa.MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


def identity() -> sa.Column[UUID]:
    return sa.Column("id", sa.Uuid, primary_key=True, default=uuid4)


def timestamp(name: str, *, nullable: bool = False) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def created() -> sa.Column[datetime]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def reference(
    name: str, target: str, *, nullable: bool = False, ondelete: str = "RESTRICT"
) -> sa.Column[UUID]:
    return sa.Column(
        name, sa.Uuid, sa.ForeignKey(target, ondelete=ondelete), nullable=nullable, index=True
    )


def document(name: str, *, nullable: bool = False) -> sa.Column[Any]:
    return sa.Column(name, JSONB, nullable=nullable)


creator_profiles = sa.Table(
    "creator_profiles",
    metadata,
    identity(),
    sa.Column("profile_key", sa.String(80), nullable=False, unique=True),
    document("configuration"),
    sa.Column("version", sa.Integer, nullable=False, default=1),
    created(),
)

budget_policies = sa.Table(
    "budget_policies",
    metadata,
    identity(),
    reference("profile_id", "creator_profiles.id"),
    sa.Column("version", sa.String(80), nullable=False),
    document("limits"),
    created(),
    sa.UniqueConstraint("profile_id", "version"),
)

production_recipes = sa.Table(
    "production_recipes",
    metadata,
    identity(),
    sa.Column("recipe_key", sa.String(120), nullable=False),
    sa.Column("version", sa.String(80), nullable=False),
    document("configuration"),
    created(),
    sa.UniqueConstraint("recipe_key", "version"),
)

provider_policies = sa.Table(
    "provider_policies",
    metadata,
    identity(),
    sa.Column("provider", sa.String(40), nullable=False),
    sa.Column("data_type", sa.String(80), nullable=False),
    sa.Column("operation", sa.String(80), nullable=False),
    sa.Column("usage", sa.String(40), nullable=False),
    sa.Column("version", sa.String(80), nullable=False),
    sa.Column("status", sa.String(20), nullable=False),
    sa.Column("evidence_source", sa.Text, nullable=False),
    sa.Column("retention_seconds", sa.Integer),
    timestamp("effective_at"),
    created(),
    sa.UniqueConstraint("provider", "data_type", "operation", "usage", "version"),
    sa.CheckConstraint("status IN ('pending', 'enabled', 'disabled')", name="status"),
    sa.CheckConstraint("retention_seconds IS NULL OR retention_seconds > 0", name="retention"),
)

seed_families = sa.Table(
    "seed_families",
    metadata,
    identity(),
    sa.Column("family_key", sa.String(80), nullable=False, unique=True),
    sa.Column("catalog_version", sa.String(80), nullable=False),
    document("configuration"),
    timestamp("last_explored_at", nullable=True),
    created(),
)

analysis_runs = sa.Table(
    "analysis_runs",
    metadata,
    identity(),
    reference("profile_id", "creator_profiles.id"),
    sa.Column("mode", sa.String(20), nullable=False),
    sa.Column("trigger", sa.String(20), nullable=False),
    sa.Column("status", sa.String(40), nullable=False),
    document("configuration"),
    document("coverage", nullable=True),
    timestamp("finished_at", nullable=True),
    created(),
    sa.CheckConstraint("mode IN ('synthetic', 'live')", name="mode"),
)

radar_schedules = sa.Table(
    "radar_schedules",
    metadata,
    identity(),
    reference("profile_id", "creator_profiles.id"),
    sa.Column("schedule_key", sa.String(100), nullable=False, unique=True),
    sa.Column("paused", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Column("interval_seconds", sa.Integer, nullable=False),
    timestamp("next_due_at"),
    document("configuration"),
    created(),
    sa.CheckConstraint("interval_seconds > 0", name="positive_interval"),
)

jobs = sa.Table(
    "jobs",
    metadata,
    identity(),
    reference("run_id", "analysis_runs.id"),
    sa.Column("occurrence_key", sa.String(200), nullable=False, unique=True),
    sa.Column("status", sa.String(40), nullable=False),
    sa.Column("stage", sa.String(40), nullable=False),
    sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    sa.Column("lease_owner", sa.String(120)),
    timestamp("lease_until", nullable=True),
    timestamp("heartbeat_at", nullable=True),
    timestamp("available_at"),
    document("checkpoints"),
    sa.Column("error_code", sa.String(100)),
    created(),
    sa.CheckConstraint("attempts >= 0", name="attempts"),
)
sa.Index("ix_jobs_claim", jobs.c.status, jobs.c.available_at, jobs.c.lease_until)

discovery_queries = sa.Table(
    "discovery_queries",
    metadata,
    identity(),
    reference("run_id", "analysis_runs.id"),
    reference("family_id", "seed_families.id"),
    sa.Column("query", sa.Text, nullable=False),
    reference("parent_query_id", "discovery_queries.id", nullable=True),
    sa.Column("selection_method", sa.String(80), nullable=False),
    created(),
)

provider_requests = sa.Table(
    "provider_requests",
    metadata,
    identity(),
    reference("run_id", "analysis_runs.id", nullable=True),
    sa.Column("provider", sa.String(40), nullable=False),
    sa.Column("operation", sa.String(80), nullable=False),
    sa.Column("auth_scope", sa.String(120), nullable=False),
    sa.Column("cache_key", sa.String(64), nullable=False, index=True),
    sa.Column("idempotency_key", sa.String(160), nullable=False, unique=True),
    sa.Column("state", sa.String(40), nullable=False),
    timestamp("sent_at", nullable=True),
    timestamp("completed_at", nullable=True),
    sa.Column("error_code", sa.String(100)),
    created(),
)

raw_observations = sa.Table(
    "raw_observations",
    metadata,
    identity(),
    reference("request_id", "provider_requests.id"),
    reference("policy_id", "provider_policies.id"),
    sa.Column("normalization_version", sa.String(80), nullable=False),
    timestamp("fetched_at"),
    timestamp("observed_at", nullable=True),
    timestamp("retain_until"),
    document("payload"),
    document("coverage"),
    created(),
    sa.CheckConstraint("retain_until > fetched_at", name="retention_deadline"),
)
sa.Index("ix_raw_observations_expiration", raw_observations.c.retain_until)

provider_cache = sa.Table(
    "provider_cache",
    metadata,
    identity(),
    sa.Column("cache_key", sa.String(64), nullable=False, unique=True),
    reference("observation_id", "raw_observations.id", ondelete="CASCADE"),
    timestamp("cache_valid_until"),
    created(),
)

channels = sa.Table(
    "channels",
    metadata,
    identity(),
    sa.Column("platform", sa.String(40), nullable=False),
    sa.Column("external_id", sa.String(120), nullable=False),
    created(),
    sa.UniqueConstraint("platform", "external_id"),
)

videos = sa.Table(
    "videos",
    metadata,
    identity(),
    sa.Column("platform", sa.String(40), nullable=False),
    sa.Column("external_id", sa.String(120), nullable=False),
    reference("channel_id", "channels.id"),
    created(),
    sa.UniqueConstraint("platform", "external_id"),
)

channel_observations = sa.Table(
    "channel_observations",
    metadata,
    identity(),
    reference("channel_id", "channels.id"),
    reference("raw_observation_id", "raw_observations.id", ondelete="CASCADE"),
    sa.Column("subscribers", sa.BigInteger),
    sa.Column("country", sa.String(8)),
    document("data"),
    timestamp("observed_at"),
    timestamp("retain_until"),
    created(),
    sa.UniqueConstraint("channel_id", "raw_observation_id"),
    sa.CheckConstraint("subscribers IS NULL OR subscribers >= 0", name="subscribers"),
)

video_observations = sa.Table(
    "video_observations",
    metadata,
    identity(),
    reference("video_id", "videos.id"),
    reference("raw_observation_id", "raw_observations.id", ondelete="CASCADE"),
    sa.Column("format", sa.String(20), nullable=False),
    sa.Column("language", sa.String(30)),
    sa.Column("views", sa.BigInteger),
    timestamp("published_at", nullable=True),
    timestamp("observed_at"),
    timestamp("retain_until"),
    document("data"),
    created(),
    sa.UniqueConstraint("video_id", "raw_observation_id"),
    sa.CheckConstraint("views IS NULL OR views >= 0", name="views"),
    sa.CheckConstraint("format IN ('long', 'shorts', 'unknown')", name="format"),
)

topics = sa.Table(
    "topics",
    metadata,
    identity(),
    reference("family_id", "seed_families.id"),
    sa.Column("label", sa.Text, nullable=True),
    sa.Column("identity_key", sa.String(160), nullable=False, unique=True),
    sa.Column("method_version", sa.String(80), nullable=False),
    timestamp("retain_until", nullable=True),
    created(),
)

topic_memberships = sa.Table(
    "topic_memberships",
    metadata,
    reference("topic_id", "topics.id", ondelete="CASCADE"),
    reference("video_id", "videos.id"),
    reference("observation_id", "raw_observations.id", ondelete="CASCADE"),
    sa.PrimaryKeyConstraint("topic_id", "video_id"),
)

topic_artifacts = sa.Table(
    "topic_artifacts",
    metadata,
    identity(),
    reference("topic_id", "topics.id", ondelete="CASCADE"),
    reference("observation_id", "raw_observations.id", ondelete="CASCADE"),
    document("data"),
    timestamp("retain_until"),
    created(),
)

cohorts = sa.Table(
    "cohorts",
    metadata,
    identity(),
    reference("run_id", "analysis_runs.id"),
    reference("topic_id", "topics.id"),
    sa.Column("format", sa.String(20), nullable=False),
    sa.Column("language", sa.String(30), nullable=False),
    document("criteria"),
    document("coverage"),
    created(),
    sa.CheckConstraint("format IN ('long', 'shorts')", name="confirmed_format"),
)

cohort_memberships = sa.Table(
    "cohort_memberships",
    metadata,
    reference("cohort_id", "cohorts.id", ondelete="CASCADE"),
    reference("video_id", "videos.id"),
    reference("video_observation_id", "video_observations.id", ondelete="CASCADE"),
    sa.Column("included", sa.Boolean, nullable=False),
    sa.Column("reason_code", sa.String(100), nullable=False),
    sa.Column("selection_method", sa.String(80), nullable=False),
    sa.Column("size_stratum", sa.String(30), nullable=False),
    sa.Column("age_band", sa.String(20), nullable=False),
    sa.PrimaryKeyConstraint("cohort_id", "video_id"),
)

opportunities = sa.Table(
    "opportunities",
    metadata,
    identity(),
    reference("topic_id", "topics.id"),
    sa.Column("audience_key", sa.String(120), nullable=False),
    sa.Column("language", sa.String(30), nullable=False),
    sa.Column("format", sa.String(20), nullable=False),
    created(),
    sa.UniqueConstraint("topic_id", "audience_key", "language", "format"),
    sa.CheckConstraint("format IN ('long', 'shorts')", name="confirmed_format"),
)

evaluation_versions = sa.Table(
    "evaluation_versions",
    metadata,
    identity(),
    reference("opportunity_id", "opportunities.id"),
    reference("cohort_id", "cohorts.id"),
    reference("run_id", "analysis_runs.id"),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("method_version", sa.String(100), nullable=False),
    sa.Column("reference_version", sa.String(100)),
    sa.Column("state", sa.String(40), nullable=False),
    sa.Column("confidence", sa.String(30), nullable=False),
    sa.Column("market_score", sa.Float),
    sa.Column("creator_fit", sa.Float),
    sa.Column("final_score", sa.Float),
    document("explanation", nullable=True),
    timestamp("retain_until"),
    timestamp("expired_at", nullable=True),
    created(),
    sa.UniqueConstraint("opportunity_id", "version"),
    sa.CheckConstraint("version > 0", name="positive_version"),
    *[
        sa.CheckConstraint(f"{name} IS NULL OR ({name} >= 0 AND {name} <= 100)", name=name)
        for name in ("market_score", "creator_fit", "final_score")
    ],
)

feature_values = sa.Table(
    "feature_values",
    metadata,
    identity(),
    reference("evaluation_id", "evaluation_versions.id", ondelete="CASCADE"),
    sa.Column("name", sa.String(120), nullable=False),
    sa.Column("value", sa.Float),
    sa.Column("unit", sa.String(80), nullable=False),
    document("definition"),
    timestamp("retain_until"),
    sa.UniqueConstraint("evaluation_id", "name"),
)

evidence_links = sa.Table(
    "evidence_links",
    metadata,
    identity(),
    reference("evaluation_id", "evaluation_versions.id", ondelete="CASCADE"),
    reference("observation_id", "raw_observations.id", nullable=True, ondelete="SET NULL"),
    sa.Column("availability", sa.String(30), nullable=False),
    sa.Column("claim_key", sa.String(120), nullable=False),
    timestamp("retain_until"),
    created(),
)

opportunity_decisions = sa.Table(
    "opportunity_decisions",
    metadata,
    identity(),
    reference("opportunity_id", "opportunities.id"),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("state", sa.String(30), nullable=False),
    sa.Column("note", sa.Text, nullable=False),
    created(),
    sa.UniqueConstraint("opportunity_id", "version"),
    sa.CheckConstraint("state IN ('new', 'watching', 'selected', 'dismissed')", name="state"),
)

budget_scenarios = sa.Table(
    "budget_scenarios",
    metadata,
    identity(),
    reference("profile_id", "creator_profiles.id"),
    sa.Column("name", sa.String(160), nullable=False),
    document("assumptions"),
    document("result", nullable=True),
    created(),
)

scenario_items = sa.Table(
    "scenario_items",
    metadata,
    identity(),
    reference("scenario_id", "budget_scenarios.id", ondelete="CASCADE"),
    sa.Column("channel_proposal_key", sa.String(120), nullable=False),
    reference("opportunity_id", "opportunities.id"),
    reference("recipe_id", "production_recipes.id"),
    document("production_plan"),
    created(),
    sa.UniqueConstraint("scenario_id", "channel_proposal_key", "opportunity_id"),
)

credit_balances = sa.Table(
    "credit_balances",
    metadata,
    identity(),
    sa.Column("provider", sa.String(40), nullable=False),
    sa.Column("auth_scope", sa.String(120), nullable=False),
    sa.Column("renewable_remaining", sa.Numeric(18, 6), nullable=False),
    sa.Column("additional_remaining", sa.Numeric(18, 6), nullable=False),
    sa.Column("renewable_allocation", sa.Numeric(18, 6), nullable=False),
    timestamp("cycle_started_at"),
    timestamp("renews_at"),
    timestamp("observed_at"),
    created(),
    sa.UniqueConstraint("provider", "auth_scope"),
    sa.CheckConstraint(
        "renewable_remaining >= 0 AND additional_remaining >= 0 AND renewable_allocation >= 0",
        name="nonnegative_balance",
    ),
    sa.CheckConstraint("renews_at > cycle_started_at", name="cycle"),
)

cost_reservations = sa.Table(
    "cost_reservations",
    metadata,
    identity(),
    reference("request_id", "provider_requests.id"),
    reference("profile_id", "creator_profiles.id"),
    sa.Column("unit", sa.String(50), nullable=False),
    sa.Column("amount", sa.Numeric(18, 6), nullable=False),
    sa.Column("status", sa.String(30), nullable=False),
    timestamp("period_start"),
    timestamp("period_end"),
    created(),
    sa.UniqueConstraint("request_id", "unit"),
    sa.CheckConstraint("amount >= 0", name="nonnegative_amount"),
    sa.CheckConstraint("period_end > period_start", name="period"),
    sa.CheckConstraint(
        "status IN ('reserved', 'confirmed', 'released', 'unknown_charge')", name="status"
    ),
)

cost_ledger = sa.Table(
    "cost_ledger",
    metadata,
    identity(),
    reference("profile_id", "creator_profiles.id"),
    reference("request_id", "provider_requests.id", nullable=True),
    sa.Column("unit", sa.String(50), nullable=False),
    sa.Column("amount", sa.Numeric(18, 6), nullable=False),
    sa.Column("kind", sa.String(40), nullable=False),
    sa.Column("external_reference", sa.String(160), nullable=False, unique=True),
    timestamp("occurred_at"),
    created(),
    sa.CheckConstraint("amount >= 0", name="nonnegative_amount"),
)
