"""Read-only operational views; internal request keys and worker identities stay private."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, collate, func, select

from nicheradar.repositories import schema_v1 as s


def job_view(row: Any) -> dict[str, Any]:
    fields = (
        "id",
        "run_id",
        "status",
        "stage",
        "attempts",
        "lease_until",
        "heartbeat_at",
        "available_at",
        "error_code",
        "created_at",
        "finished_at",
        "source_mode",
        "coverage",
    )
    return {key: row[key] for key in fields} | {"completed_stages": list(row["checkpoints"])}


def jobs(
    connection: Connection, *, limit: int = 20, offset: int = 0, job_id: UUID | None = None
) -> dict[str, Any]:
    statement = select(
        s.jobs,
        s.analysis_runs.c.coverage,
        s.analysis_runs.c.finished_at,
        s.analysis_runs.c.mode.label("source_mode"),
    ).join(s.analysis_runs, s.analysis_runs.c.id == s.jobs.c.run_id)
    if job_id is not None:
        statement = statement.where(s.jobs.c.id == job_id)
    total = connection.execute(select(func.count()).select_from(statement.subquery())).scalar_one()
    rows = (
        connection.execute(
            statement.order_by(s.jobs.c.created_at.desc(), s.jobs.c.id).limit(limit).offset(offset)
        )
        .mappings()
        .all()
    )
    # Aggregate only the visible page, independently: joining ledger and reservations
    # together would multiply charges when a request has several accounting units.
    costs: dict[UUID, dict[str, list[dict[str, Any]]]] = {
        row["run_id"]: {"confirmed": [], "reservations": []} for row in rows
    }
    if costs:
        for table, bucket in (
            (s.cost_ledger, "confirmed"),
            (s.cost_reservations, "reservations"),
        ):
            columns = [s.provider_requests.c.run_id, table.c.unit]
            if bucket == "reservations":
                columns.append(table.c.status)
            query = (
                select(*columns, func.sum(table.c.amount).label("amount"))
                .join(s.provider_requests, s.provider_requests.c.id == table.c.request_id)
                .where(s.provider_requests.c.run_id.in_(costs))
                .group_by(*columns)
                # "C" keeps the unit order identical whatever collation the database uses.
                .order_by(s.provider_requests.c.run_id, collate(table.c.unit, "C"), *columns[2:])
            )
            if bucket == "reservations":
                query = query.where(table.c.status.in_(["reserved", "unknown_charge"]))
            for cost in connection.execute(query).mappings():
                costs[cost["run_id"]][bucket].append(
                    {key: value for key, value in cost.items() if key != "run_id"}
                )
    return {
        "items": [job_view(row) | {"consumption": costs[row["run_id"]]} for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def overview(
    connection: Connection,
    profile_id: UUID,
    mode: str,
    now: datetime,
    *,
    provider_ready: bool | None = None,
) -> dict[str, Any]:
    latest = (
        select(s.evaluation_versions)
        .join(s.analysis_runs, s.analysis_runs.c.id == s.evaluation_versions.c.run_id)
        .where(s.analysis_runs.c.profile_id == profile_id, s.analysis_runs.c.mode == mode)
        .distinct(s.evaluation_versions.c.opportunity_id)
        .order_by(s.evaluation_versions.c.opportunity_id, s.evaluation_versions.c.version.desc())
        .subquery()
    )
    valid = (latest.c.expired_at.is_(None)) & (latest.c.retain_until > now)
    counts = (
        connection.execute(
            select(
                func.count().label("evaluations"),
                func.count().filter(valid).label("retained"),
                func.count().filter(valid & latest.c.final_score.is_not(None)).label("scored"),
                func.max(latest.c.created_at).label("last_evaluated_at"),
            )
        )
        .mappings()
        .one()
    )
    last_job = (
        connection.execute(
            select(s.jobs.c.id, s.jobs.c.status, s.jobs.c.error_code, s.analysis_runs.c.coverage)
            .join(s.analysis_runs, s.analysis_runs.c.id == s.jobs.c.run_id)
            .where(s.analysis_runs.c.profile_id == profile_id, s.analysis_runs.c.mode == mode)
            .order_by(s.jobs.c.created_at.desc(), s.jobs.c.id)
            .limit(1)
        )
        .mappings()
        .first()
    )
    data_at = connection.execute(
        select(func.max(s.video_observations.c.observed_at))
        .join(
            s.raw_observations, s.raw_observations.c.id == s.video_observations.c.raw_observation_id
        )
        .join(s.provider_requests, s.provider_requests.c.id == s.raw_observations.c.request_id)
        .join(s.analysis_runs, s.analysis_runs.c.id == s.provider_requests.c.run_id)
        .where(
            s.analysis_runs.c.profile_id == profile_id,
            s.analysis_runs.c.mode == mode,
            s.video_observations.c.retain_until > now,
            s.raw_observations.c.retain_until > now,
        )
    ).scalar_one()
    reasons = []
    if mode == "live" and provider_ready is not True:
        reasons.append("provider_pending")
    code = (
        (last_job["error_code"] or (last_job["coverage"] or {}).get("pending_reason"))
        if last_job
        else None
    )
    if code in {
        "balance_exhausted",
        "run_budget_exhausted",
        "period_budget_exhausted",
        "shared_budget_exhausted",
        "quota",
        "unknown_charge",
    }:
        reasons.append("budget_blocked")
    elif code in {
        "policy_pending",
        "policy_disabled",
        "live_connection_pending",
        "live_prerequisites_incomplete",
        "account_scope_required",
        "provider_mode_mismatch",
        "authentication_required",
        "budget_confirmation_required",
        "balance_refresh_required",
        "unknown_cost",
    }:
        reasons.append("configuration_pending")
    elif code in {"refresh_evidence_insufficient", "batch_limit"} or (
        last_job and last_job["status"] == "partial" and not code
    ):
        reasons.append("coverage_pending")
    elif last_job and (last_job["status"] == "failed" or code):
        reasons.append("technical_error")
    if last_job and last_job["status"] in {"queued", "running"}:
        reasons.append("processing")
    if counts["evaluations"] == 0:
        reasons.append("no_results")
    elif counts["retained"] == 0:
        reasons.append("evidence_expired")
    elif counts["scored"] == 0:
        reasons.append("evaluation_pending")
    return dict(counts) | {
        "mode": mode,
        "reasons": reasons,
        "last_job_id": last_job["id"] if last_job else None,
        "last_error_code": code,
        "last_observed_at": data_at,
        "observation_age_hours": max(0, (now - data_at).total_seconds() / 3600)
        if data_at
        else None,
    }
