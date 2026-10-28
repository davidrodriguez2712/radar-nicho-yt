"""Expire evidence and derived content in one transaction; log only aggregate counts."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import Connection, delete, func, or_, select, update

from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.schema import (
    balance_reconciliations,
    channel_analyses,
    credit_balances,
    flow_research_dossiers,
    flow_research_requests,
    listing_channel_snapshots,
    listing_classifications,
    listing_evidence,
    listing_observations,
    listing_verifications,
    market_niche_snapshots,
    marketplace_listings,
    opportunity_scoring_configs,
    ranking_entries,
    ranking_snapshots,
    topic_artifact_sources,
)


def shorten_policy_retention(
    connection: Connection, old_policy_id: UUID, retention_seconds: int, now: datetime
) -> int:
    if retention_seconds < 0:
        raise ValueError("retention cannot be negative")
    rows = (
        connection.execute(
            select(s.raw_observations).where(s.raw_observations.c.policy_id == old_policy_id)
        )
        .mappings()
        .all()
    )
    affected = 0
    revoked = []
    for row in rows:
        if retention_seconds == 0:
            revoked.append(row["id"])
            affected += 1
            continue
        deadline = min(
            row["retain_until"], row["fetched_at"] + timedelta(seconds=retention_seconds)
        )
        if deadline < row["retain_until"]:
            connection.execute(
                update(s.raw_observations)
                .where(s.raw_observations.c.id == row["id"])
                .values(retain_until=deadline)
            )
            affected += 1
    # A shorter source deadline also shortens retained balance snapshots and differences.
    source_deadline = (
        select(s.raw_observations.c.retain_until)
        .where(s.raw_observations.c.id == credit_balances.c.source_observation_id)
        .scalar_subquery()
    )
    connection.execute(
        update(credit_balances)
        .where(credit_balances.c.source_observation_id.is_not(None))
        .values(retain_until=func.least(credit_balances.c.retain_until, source_deadline))
    )
    for source_column in (
        balance_reconciliations.c.source_observation_id,
        balance_reconciliations.c.previous_observation_id,
    ):
        deadline = (
            select(s.raw_observations.c.retain_until)
            .where(s.raw_observations.c.id == source_column)
            .scalar_subquery()
        )
        connection.execute(
            update(balance_reconciliations)
            .where(source_column.is_not(None))
            .values(retain_until=func.least(balance_reconciliations.c.retain_until, deadline))
        )
    expire(connection, now, revoked_observation_ids=tuple(revoked))
    return affected


def expire(
    connection: Connection, now: datetime, *, revoked_observation_ids: tuple[UUID, ...] = ()
) -> dict[str, int]:
    connection.execute(
        delete(marketplace_listings).where(marketplace_listings.c.retain_until <= now)
    )
    for child in (
        listing_observations,
        listing_classifications,
        listing_verifications,
        listing_channel_snapshots,
        listing_evidence,
    ):
        # Children carry their own deadline: a listing that stays up must not keep old rows.
        connection.execute(delete(child).where(child.c.retain_until <= now))
    connection.execute(
        delete(market_niche_snapshots).where(market_niche_snapshots.c.retain_until <= now)
    )
    connection.execute(
        delete(flow_research_dossiers).where(flow_research_dossiers.c.retain_until <= now)
    )
    connection.execute(
        delete(flow_research_requests).where(
            flow_research_requests.c.retain_until <= now,
            # A request whose dossier is still retained must outlive it (foreign key).
            flow_research_requests.c.id.not_in(select(flow_research_dossiers.c.request_id)),
        )
    )
    connection.execute(
        delete(balance_reconciliations).where(balance_reconciliations.c.retain_until <= now)
    )
    connection.execute(delete(credit_balances).where(credit_balances.c.retain_until <= now))
    connection.execute(
        update(opportunity_scoring_configs)
        .where(
            opportunity_scoring_configs.c.retain_until <= now,
            opportunity_scoring_configs.c.expired_at.is_(None),
        )
        .values(configuration=None, expired_at=now)
    )
    # The snapshot holds retained YouTube/vidIQ metadata; configuration/consumption are
    # NOT NULL and kept as a small audit trail of what was asked and what it cost.
    connection.execute(
        update(channel_analyses)
        .where(channel_analyses.c.retain_until <= now, channel_analyses.c.expired_at.is_(None))
        .values(snapshot=None, expired_at=now)
    )
    due = or_(
        s.raw_observations.c.retain_until <= now,
        s.raw_observations.c.id.in_(revoked_observation_ids),
    )
    due_raw = select(s.raw_observations.c.id).where(due)
    affected_evaluations = select(s.evidence_links.c.evaluation_id).where(
        or_(s.evidence_links.c.observation_id.in_(due_raw), s.evidence_links.c.retain_until <= now)
    )
    expired_evaluations = list(
        connection.execute(
            select(s.evaluation_versions.c.id).where(
                or_(
                    s.evaluation_versions.c.retain_until <= now,
                    s.evaluation_versions.c.id.in_(affected_evaluations),
                ),
                s.evaluation_versions.c.expired_at.is_(None),
            )
        ).scalars()
    )
    if expired_evaluations:
        connection.execute(
            delete(s.feature_values).where(
                s.feature_values.c.evaluation_id.in_(expired_evaluations)
            )
        )
        connection.execute(
            update(s.evaluation_versions)
            .where(s.evaluation_versions.c.id.in_(expired_evaluations))
            .values(
                market_score=None,
                creator_fit=None,
                final_score=None,
                explanation=None,
                state="insufficient_evidence",
                confidence="insufficient",
                expired_at=now,
            )
        )
        connection.execute(
            update(s.evidence_links)
            .where(s.evidence_links.c.evaluation_id.in_(expired_evaluations))
            .values(observation_id=None, availability="expired")
        )
    invalid_rankings = (
        select(ranking_entries.c.snapshot_id)
        .join(s.evaluation_versions, s.evaluation_versions.c.id == ranking_entries.c.evaluation_id)
        .where(s.evaluation_versions.c.expired_at.is_not(None))
    )
    expired_rankings = list(
        connection.execute(
            select(ranking_snapshots.c.id).where(
                ranking_snapshots.c.expired_at.is_(None),
                or_(
                    ranking_snapshots.c.retain_until <= now,
                    ranking_snapshots.c.id.in_(invalid_rankings),
                ),
            )
        ).scalars()
    )
    if expired_rankings:
        connection.execute(
            delete(ranking_entries).where(ranking_entries.c.snapshot_id.in_(expired_rankings))
        )
        connection.execute(
            update(ranking_snapshots)
            .where(ranking_snapshots.c.id.in_(expired_rankings))
            .values(expired_at=now)
        )
    affected_artifacts = select(topic_artifact_sources.c.artifact_id).where(
        topic_artifact_sources.c.observation_id.in_(due_raw)
    )
    artifact_due = or_(
        s.topic_artifacts.c.retain_until <= now,
        s.topic_artifacts.c.observation_id.in_(due_raw),
        s.topic_artifacts.c.id.in_(affected_artifacts),
    )
    affected_topics = select(s.topic_artifacts.c.topic_id).where(artifact_due)
    connection.execute(
        update(s.topics)
        .where(or_(s.topics.c.id.in_(affected_topics), s.topics.c.retain_until <= now))
        .values(label=None)
    )
    connection.execute(delete(s.topic_artifacts).where(artifact_due))
    for table in (s.video_observations, s.channel_observations, s.feature_values):
        connection.execute(delete(table).where(table.c.retain_until <= now))
    result = connection.execute(delete(s.raw_observations).where(due))
    return {
        "expired_observations": result.rowcount,
        "expired_evaluations": len(expired_evaluations),
    }
