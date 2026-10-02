"""Persistent work selection, scoped by profile and synthetic/live mode."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, func, select, update
from sqlalchemy.dialects.postgresql import insert

from nicheradar.domain.profile import CreatorProfile
from nicheradar.integrations.contracts import ProviderError
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record
from nicheradar.repositories.schema import discovery_cursors as cursors
from nicheradar.services.backlog import latest_decision
from nicheradar.services.budget import lock_profile


def plan_family(
    connection: Connection,
    profile_id: UUID,
    run_id: UUID,
    now: datetime,
    exploration_share: Decimal = Decimal(".25"),
) -> dict[str, Any]:
    lock_profile(connection, profile_id)
    run = (
        connection.execute(select(s.analysis_runs).where(s.analysis_runs.c.id == run_id))
        .mappings()
        .one()
    )
    profile = CreatorProfile.model_validate(
        connection.execute(
            select(s.creator_profiles.c.configuration).where(s.creator_profiles.c.id == profile_id)
        ).scalar_one()
    )
    families = {
        row["id"]: dict(row) for row in connection.execute(select(s.seed_families)).mappings()
    }
    if not families:
        raise ValueError("seed catalog has not been initialized")
    for family_id in families:
        connection.execute(
            insert(cursors)
            .values(
                profile_id=profile_id,
                mode=run["mode"],
                family_id=family_id,
                work_key=f"catalog:{family_id}",
            )
            .on_conflict_do_nothing()
        )
    candidates = []
    for row in connection.execute(
        select(s.opportunities, s.topics.c.family_id).join(
            s.topics, s.topics.c.id == s.opportunities.c.topic_id
        )
    ).mappings():
        decision = latest_decision(connection, row["id"])
        if (
            decision["state"] not in {"selected", "watching"}
            or row["format"] not in profile.formats
            or row["language"] != profile.language
        ):
            continue
        evaluation = (
            connection.execute(
                select(s.evaluation_versions)
                .join(s.analysis_runs, s.analysis_runs.c.id == s.evaluation_versions.c.run_id)
                .where(
                    s.evaluation_versions.c.opportunity_id == row["id"],
                    s.analysis_runs.c.profile_id == profile_id,
                    s.analysis_runs.c.mode == run["mode"],
                )
                .order_by(s.evaluation_versions.c.version.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if evaluation is None:
            continue
        fetched_at = connection.execute(
            select(func.min(s.raw_observations.c.fetched_at))
            .join(s.evidence_links, s.evidence_links.c.observation_id == s.raw_observations.c.id)
            .where(s.evidence_links.c.evaluation_id == evaluation["id"])
        ).scalar_one()
        connection.execute(
            insert(cursors)
            .values(
                profile_id=profile_id,
                mode=run["mode"],
                family_id=row["family_id"],
                opportunity_id=row["id"],
                work_key=f"refresh:{row['id']}",
            )
            .on_conflict_do_nothing()
        )
        candidates.append(
            dict(row)
            | {"review_state": decision["state"], "data_at": fetched_at or evaluation["created_at"]}
        )
    work = [
        dict(row)
        for row in connection.execute(
            select(cursors).where(cursors.c.profile_id == profile_id, cursors.c.mode == run["mode"])
        ).mappings()
    ]
    candidates_by_id = {row["id"]: row for row in candidates}
    usable = []
    for cursor in work:
        pending = None
        if cursor["pending_job_id"]:
            pending = (
                connection.execute(select(s.jobs).where(s.jobs.c.id == cursor["pending_job_id"]))
                .mappings()
                .first()
            )
            if pending and pending["status"] in {"queued", "running"}:
                continue
        cursor["pending_job"] = dict(pending) if pending else None
        if cursor["opportunity_id"]:
            candidate = candidates_by_id.get(cursor["opportunity_id"])
            if candidate is None:
                continue
            interval = (
                profile.selected_refresh_hours
                if candidate["review_state"] == "selected"
                else profile.watching_refresh_hours
            )
            last = max(
                candidate["data_at"], cursor["last_attempt_at"] or datetime.min.replace(tzinfo=UTC)
            )
            if not pending and last + timedelta(hours=interval) > now:
                continue
            cursor["candidate"] = candidate
        usable.append(cursor)
    catalog = sorted(
        (row for row in usable if not row["opportunity_id"]),
        key=lambda row: (
            row["last_attempt_at"] or datetime.min.replace(tzinfo=UTC),
            families[row["family_id"]]["family_key"],
        ),
    )
    refresh = sorted(
        (row for row in usable if row["opportunity_id"]),
        key=lambda row: (
            row["candidate"]["review_state"] != "selected",
            row["last_attempt_at"] or row["candidate"]["data_at"],
            str(row["id"]),
        ),
    )
    calls = connection.execute(
        select(
            s.analysis_runs.c.configuration["discovery_kind"].astext.label("kind"),
            func.count(s.provider_requests.c.id),
        )
        .join(s.provider_requests, s.provider_requests.c.run_id == s.analysis_runs.c.id)
        .where(
            s.analysis_runs.c.profile_id == profile_id,
            s.analysis_runs.c.mode == run["mode"],
            s.provider_requests.c.sent_at.is_not(None),
        )
        .group_by("kind")
    ).all()
    total = sum(count for _, count in calls)
    explored = sum(count for kind, count in calls if kind != "refresh")
    exploration_slot = total == 0 or Decimal(explored) < exploration_share * total
    pending_catalog = [
        row
        for row in catalog
        if row["pending_job"] or families[row["family_id"]]["configuration"].get("pending")
    ]
    chosen = (
        catalog[0]
        if exploration_slot and catalog
        else refresh[0]
        if refresh
        else pending_catalog[0]
        if pending_catalog
        else catalog[0]
        if catalog
        else None
    )
    if chosen is None:
        raise ProviderError("discovery_work_in_progress")
    family = families[chosen["family_id"]]
    kind = "refresh" if chosen["opportunity_id"] else "catalog"
    pending = chosen["pending_job"]
    previous_plan = pending["checkpoints"].get("planning", {}) if pending else {}
    query_index = previous_plan.get("query_index", 0)
    query = family["configuration"]["queries"][query_index]
    query_id = insert_record(
        connection,
        "discovery_queries",
        {
            "run_id": run_id,
            "family_id": family["id"],
            "query": query,
            "selection_method": "continuation" if pending else kind,
            "created_at": now,
        },
    )
    job_id = connection.execute(select(s.jobs.c.id).where(s.jobs.c.run_id == run_id)).scalar_one()
    connection.execute(
        update(cursors)
        .where(cursors.c.id == chosen["id"])
        .values(last_attempt_at=now, pending_job_id=job_id)
    )
    connection.execute(
        update(s.analysis_runs)
        .where(s.analysis_runs.c.id == run_id)
        .values(configuration=run["configuration"] | {"discovery_kind": kind})
    )
    if kind == "catalog":
        connection.execute(
            update(s.seed_families)
            .where(s.seed_families.c.id == family["id"])
            .values(last_explored_at=now)
        )
    candidate = chosen.get("candidate", {})
    # A completed query sequence with insufficient refresh evidence needs a new
    # cache-aware attempt, not perpetual reuse of empty retained receipts.
    reusable_pending = pending and not (
        kind == "refresh" and pending["checkpoints"].get("query", {}).get("complete", False)
    )
    return {
        "family_id": str(family["id"]),
        "family_key": family["family_key"],
        "query": query,
        "query_id": str(query_id),
        "query_index": query_index,
        "kind": kind,
        "cursor_id": str(chosen["id"]),
        "opportunity_id": str(chosen["opportunity_id"]) if chosen["opportunity_id"] else None,
        "target_topic_id": str(candidate["topic_id"]) if candidate else None,
        "target_format": candidate.get("format"),
        "source_job_id": str(pending["id"]) if reusable_pending else None,
        "pending": bool(pending),
        "catalog_pending": [
            row["family_key"] for key, row in families.items() if key != family["id"]
        ],
        "refresh_pending": [
            str(row["opportunity_id"]) for row in refresh if row["id"] != chosen["id"]
        ],
    }


def finish_work(
    connection: Connection, plan: dict[str, Any], now: datetime, complete: bool
) -> None:
    if not complete:
        return
    connection.execute(
        update(cursors)
        .where(cursors.c.id == UUID(plan["cursor_id"]))
        .values(pending_job_id=None, completed_at=now)
    )
