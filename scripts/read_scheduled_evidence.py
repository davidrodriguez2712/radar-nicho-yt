"""Emit aggregate evidence for the latest scheduled live run without provider payloads."""

import json
import re
import sys
from collections import Counter
from uuid import UUID

from sqlalchemy import func, select

from nicheradar.config import Settings
from nicheradar.discovery.sampling import relevance
from nicheradar.integrations.contracts import Batch
from nicheradar.repositories import schema as current
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.database import database_engine

engine = database_engine(Settings())
offset = int(sys.argv[1]) if len(sys.argv) > 1 else 0
if not 0 <= offset <= 20:
    raise SystemExit("scheduled evidence offset must be between 0 and 20")
with engine.connect() as connection:
    job = (
        connection.execute(
            select(
                s.jobs,
                s.analysis_runs.c.mode,
                s.analysis_runs.c.trigger,
                s.analysis_runs.c.coverage,
                s.analysis_runs.c.finished_at,
            )
            .join(s.analysis_runs, s.analysis_runs.c.id == s.jobs.c.run_id)
            .where(s.analysis_runs.c.mode == "live", s.analysis_runs.c.trigger == "scheduled")
            .order_by(s.jobs.c.created_at.desc(), s.jobs.c.id)
            .offset(offset)
            .limit(1)
        )
        .mappings()
        .one()
    )
    requests = (
        connection.execute(
            select(
                s.provider_requests.c.operation,
                s.provider_requests.c.state,
                s.provider_requests.c.sent_at,
            )
            .where(s.provider_requests.c.run_id == job["run_id"])
            .order_by(s.provider_requests.c.created_at, s.provider_requests.c.id)
        )
        .mappings()
        .all()
    )
    balance_payloads = connection.execute(
        select(s.raw_observations.c.payload)
        .join(s.provider_requests, s.provider_requests.c.id == s.raw_observations.c.request_id)
        .where(
            s.provider_requests.c.run_id == job["run_id"],
            s.provider_requests.c.operation == "balance",
        )
        .order_by(s.raw_observations.c.fetched_at, s.raw_observations.c.id)
    ).scalars()
    balance_snapshots = []
    for payload in balance_payloads:
        observed = Batch.model_validate(payload).balance
        if observed is not None:
            balance_snapshots.append(
                {
                    "renewable": observed.renewable,
                    "additional": observed.additional,
                    "total": observed.renewable + observed.additional,
                    "allocation": observed.recurring_allocation,
                    "renews_at": observed.renews_at,
                }
            )
    raw_ids = job["checkpoints"].get("query", {}).get("raw_ids", [])
    research_payloads = (
        connection.execute(
            select(s.raw_observations.c.payload)
            .where(s.raw_observations.c.id.in_([UUID(raw_id) for raw_id in raw_ids]))
            .order_by(s.raw_observations.c.fetched_at, s.raw_observations.c.id)
        ).scalars()
        if raw_ids
        else []
    )
    research_batches = [Batch.model_validate(payload) for payload in research_payloads]
    english_channels = {
        channel.id
        for batch in research_batches
        for channel in batch.channels
        if "en" in channel.content_languages
    }
    videos = {video.id: video for batch in research_batches for video in batch.videos}
    plan = job["checkpoints"].get("planning", {})
    query = str(plan.get("query", ""))
    query_terms = tuple(re.findall(r"[a-z0-9]+", query.casefold()))
    relevance_diagnostic = {
        "videos": len(videos),
        "english_channel_claims": sum(
            video.channel_id in english_channels for video in videos.values()
        ),
        "family_key": dict(
            Counter(
                relevance(video, (str(plan.get("family_key", "")),)) for video in videos.values()
            )
        ),
        "query_phrase": dict(Counter(relevance(video, (query,)) for video in videos.values())),
        "query_tokens": dict(Counter(relevance(video, query_terms) for video in videos.values())),
        "eligible_if_channel_language_inherited": dict(
            Counter(
                video.format.value
                for video in videos.values()
                if video.channel_id in english_channels
                and relevance(video, query_terms) == "confirmed"
            )
        ),
    }
    confirmed = connection.execute(
        select(func.coalesce(func.sum(s.cost_ledger.c.amount), 0)).where(
            s.cost_ledger.c.request_id.in_(
                select(s.provider_requests.c.id).where(
                    s.provider_requests.c.run_id == job["run_id"]
                )
            ),
            s.cost_ledger.c.unit == "vidiq_credit",
        )
    ).scalar_one()
    unresolved = connection.execute(
        select(func.count())
        .select_from(s.cost_reservations)
        .where(
            s.cost_reservations.c.request_id.in_(
                select(s.provider_requests.c.id).where(
                    s.provider_requests.c.run_id == job["run_id"]
                )
            ),
            s.cost_reservations.c.status.in_(["reserved", "unknown_charge"]),
        )
    ).scalar_one()
    balance = (
        connection.execute(
            select(current.credit_balances).where(
                current.credit_balances.c.provider == "vidiq",
                current.credit_balances.c.auth_scope == "personal-primary",
            )
        )
        .mappings()
        .one()
    )
    schedule = connection.execute(select(s.radar_schedules)).mappings().one()
    ranking_id = job["checkpoints"].get("backlog", {}).get("ranking_snapshot_id")
    ranking_entries = (
        connection.execute(
            select(func.count())
            .select_from(current.ranking_entries)
            .where(current.ranking_entries.c.snapshot_id == ranking_id)
        ).scalar_one()
        if ranking_id
        else None
    )
    ranking = (
        connection.execute(
            select(
                current.ranking_entries.c.position,
                current.ranking_entries.c.review_state,
                current.ranking_entries.c.reason,
                s.topics.c.label,
                s.opportunities.c.format,
                s.evaluation_versions.c.state,
                s.evaluation_versions.c.confidence,
                s.evaluation_versions.c.market_score,
                s.evaluation_versions.c.creator_fit,
                s.evaluation_versions.c.final_score,
                s.cohorts.c.coverage,
            )
            .select_from(current.ranking_entries)
            .join(
                s.evaluation_versions,
                s.evaluation_versions.c.id == current.ranking_entries.c.evaluation_id,
            )
            .join(s.opportunities, s.opportunities.c.id == current.ranking_entries.c.opportunity_id)
            .join(s.topics, s.topics.c.id == s.opportunities.c.topic_id)
            .join(s.cohorts, s.cohorts.c.id == s.evaluation_versions.c.cohort_id)
            .where(current.ranking_entries.c.snapshot_id == ranking_id)
            .order_by(current.ranking_entries.c.position, s.opportunities.c.format)
        )
        .mappings()
        .all()
        if ranking_id
        else []
    )
    cohort_reasons = connection.execute(
        select(
            s.cohorts.c.format,
            s.cohort_memberships.c.reason_code,
            func.count().label("count"),
        )
        .join(s.cohort_memberships, s.cohort_memberships.c.cohort_id == s.cohorts.c.id)
        .where(s.cohorts.c.run_id == job["run_id"])
        .group_by(s.cohorts.c.format, s.cohort_memberships.c.reason_code)
        .order_by(s.cohorts.c.format, s.cohort_memberships.c.reason_code)
    ).mappings()

output = {
    "job_id": job["id"],
    "run_id": job["run_id"],
    "status": job["status"],
    "mode": job["mode"],
    "trigger": job["trigger"],
    "created_at": job["created_at"],
    "finished_at": job["finished_at"],
    "completed_stages": list(job["checkpoints"]),
    "coverage": job["coverage"],
    "provider_calls": sum(row["sent_at"] is not None for row in requests),
    "operations": dict(Counter(row["operation"] for row in requests)),
    "request_states": dict(Counter(row["state"] for row in requests)),
    "credits_confirmed": confirmed,
    "unresolved_reservations": unresolved,
    "balance_snapshots": balance_snapshots,
    "balance": {
        "renewable": balance["renewable_remaining"],
        "additional": balance["additional_remaining"],
        "total": balance["renewable_remaining"] + balance["additional_remaining"],
        "allocation": balance["renewable_allocation"],
        "observed_at": balance["observed_at"],
        "renews_at": balance["renews_at"],
    },
    "relevance_diagnostic": relevance_diagnostic,
    "backlog": {
        "ranking_snapshot_id": ranking_id,
        "ranking_entries": ranking_entries,
        "evaluation_ids": job["checkpoints"].get("backlog", {}).get("evaluation_ids", []),
        "items": [dict(row) for row in ranking],
        "membership_reasons": [dict(row) for row in cohort_reasons],
    },
    "schedule": {
        "paused": schedule["paused"],
        "mode": schedule["configuration"].get("mode"),
        "interval_seconds": schedule["interval_seconds"],
        "next_due_at": schedule["next_due_at"],
    },
}
print(json.dumps(output, default=str))
