"""Prepare an isolated restored database before starting API or worker processes."""

import argparse
import json
from datetime import UTC, datetime

from sqlalchemy import Connection, func, select, update

from nicheradar.config import Settings
from nicheradar.integrations.retention import expire
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.database import database_engine
from nicheradar.repositories.schema import (
    balance_reconciliations,
    credit_balances,
    discovery_cursors,
    flow_research_dossiers,
    flow_research_requests,
    listing_classifications,
    listing_evidence,
    listing_observations,
    listing_verifications,
    market_intel_schedule,
    market_niche_snapshots,
    marketplace_listings,
    opportunity_scoring_configs,
    ranking_snapshots,
)


def backup_deadline(connection: Connection) -> datetime | None:
    """An immutable dump cannot retain any evidence past its earliest deadline."""
    deadlines = [
        value
        for table in (
            s.raw_observations,
            s.channel_observations,
            s.video_observations,
            s.topic_artifacts,
            s.topics,
            s.evaluation_versions,
            s.feature_values,
            s.evidence_links,
            credit_balances,
            balance_reconciliations,
            opportunity_scoring_configs,
            ranking_snapshots,
            marketplace_listings,
            listing_observations,
            listing_classifications,
            listing_verifications,
            listing_evidence,
            market_niche_snapshots,
            flow_research_requests,
            flow_research_dossiers,
        )
        if (value := connection.execute(select(func.min(table.c.retain_until))).scalar_one())
        is not None
    ]
    return min(deadlines) if deadlines else None


def prepare_restore(connection: Connection, now: datetime) -> dict[str, int]:
    """Caller must use an isolated target, no running workers, and commit before startup.

    A snapshot is not a payment receipt: even a prepared request could have been
    sent by the original instance after the snapshot. Never release its liability.
    """
    schedules = connection.execute(update(s.radar_schedules).values(paused=True)).rowcount
    market_schedules = connection.execute(
        update(market_intel_schedule).values(paused=True)
    ).rowcount
    connection.execute(update(discovery_cursors).values(pending_job_id=None))
    pending = list(
        connection.execute(
            select(s.provider_requests.c.id)
            .where(s.provider_requests.c.state.in_(["prepared", "sent"]))
            .with_for_update()
        ).scalars()
    )
    if pending:
        connection.execute(
            update(s.provider_requests)
            .where(s.provider_requests.c.id.in_(pending))
            .values(state="unknown_charge", error_code="restore_reconciliation_required")
        )
        connection.execute(
            update(s.cost_reservations)
            .where(
                s.cost_reservations.c.request_id.in_(pending),
                s.cost_reservations.c.status == "reserved",
            )
            .values(status="unknown_charge")
        )
    unfinished_runs = list(
        connection.execute(
            select(s.jobs.c.run_id).where(
                s.jobs.c.status.not_in(["succeeded", "failed", "cancelled"])
            )
        ).scalars()
    )
    jobs = connection.execute(
        update(s.jobs)
        .where(s.jobs.c.run_id.in_(unfinished_runs))
        .values(
            status="deferred",
            lease_owner=None,
            lease_until=None,
            heartbeat_at=None,
            error_code="restore_review_required",
        )
    ).rowcount
    connection.execute(
        update(s.analysis_runs)
        .where(s.analysis_runs.c.id.in_(unfinished_runs))
        .values(status="deferred")
    )
    connection.execute(update(credit_balances).values(refresh_required=True))
    for row in connection.execute(select(s.creator_profiles)).mappings().all():
        connection.execute(
            update(s.creator_profiles)
            .where(s.creator_profiles.c.id == row["id"])
            .values(
                configuration=row["configuration"] | {"paid_limits_confirmed": False},
                version=row["version"] + 1,
            )
        )
    return {
        "paused_schedules": schedules,
        "paused_market_schedules": market_schedules,
        "deferred_jobs": jobs,
        "uncertain_requests": len(pending),
        **expire(connection, now),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare an isolated restored NicheRadar database")
    parser.add_argument("--confirm-isolated-restore", action="store_true", required=True)
    args = parser.parse_args()
    if not args.confirm_isolated_restore:
        parser.error("explicit isolated restore confirmation required")
    config = Settings()
    engine = database_engine(config)
    try:
        with engine.begin() as connection:
            report = prepare_restore(connection, datetime.now(UTC))
        print(json.dumps(report))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
