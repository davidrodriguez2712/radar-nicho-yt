from datetime import UTC, datetime, timedelta
from random import SystemRandom
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from nicheradar.integrations.contracts import ProviderError
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record
from nicheradar.services.budget import lock_profile, settle
from nicheradar.services.requests import recover_uncertain_requests

QUEUE_LOCK = 724_619_013
STAGES = (
    "planning",
    "query",
    "enrichment",
    "normalization",
    "cohort",
    "metrics",
    "evaluation",
    "backlog",
)
BLOCKED_ERRORS = frozenset(
    {
        "unknown_cost",
        "policy_pending",
        "policy_disabled",
        "balance_exhausted",
        "run_budget_exhausted",
        "period_budget_exhausted",
        "shared_budget_exhausted",
        "budget_confirmation_required",
        "live_connection_pending",
        "live_prerequisites_incomplete",
        "account_scope_required",
        "provider_mode_mismatch",
        "unsupported_runtime_mode",
        "balance_refresh_required",
        "balance_cycle_required",
        "balance_unit_mismatch",
        "balance_source_mismatch",
        "balance_not_finite_or_dated",
        "stale_balance_observation",
        "authentication_required",
        "quota",
        "unknown_charge",
        "request_requires_reconciliation",
    }
)
ATTENTION_ERRORS = BLOCKED_ERRORS - {
    "balance_exhausted",
    "run_budget_exhausted",
    "period_budget_exhausted",
    "shared_budget_exhausted",
}


def finish_failed_requests(connection: Connection, run_id: UUID, now: datetime) -> None:
    profile_id = connection.execute(
        select(s.analysis_runs.c.profile_id).where(s.analysis_runs.c.id == run_id)
    ).scalar_one()
    lock_profile(connection, profile_id)
    recover_uncertain_requests(connection, run_id)
    prepared = list(
        connection.execute(
            select(s.provider_requests.c.id)
            .where(
                s.provider_requests.c.run_id == run_id,
                s.provider_requests.c.state == "prepared",
                s.provider_requests.c.sent_at.is_(None),
            )
            .with_for_update()
        ).scalars()
    )
    for request_id in prepared:
        settle(connection, request_id, profile_id, None, now, not_sent=True)


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("an aware scheduling timestamp is required")
    return value.astimezone(UTC)


def enqueue(
    connection: Connection,
    profile_id: UUID,
    key: str,
    now: datetime,
    configuration: dict[str, Any],
    *,
    trigger: str = "manual",
    mode: str = "synthetic",
) -> UUID:
    now = utc(now)
    # Shared scheduler lock also serializes idempotent manual occurrence creation.
    connection.execute(select(func.pg_advisory_xact_lock(QUEUE_LOCK)))
    existing = connection.execute(
        select(s.jobs.c.id).where(s.jobs.c.occurrence_key == key)
    ).scalar()
    if existing:
        return UUID(str(existing))
    run_id = insert_record(
        connection,
        "analysis_runs",
        {
            "profile_id": profile_id,
            "mode": mode,
            "trigger": trigger,
            "status": "queued",
            "configuration": configuration,
            "created_at": now,
        },
    )
    return insert_record(
        connection,
        "jobs",
        {
            "run_id": run_id,
            "occurrence_key": key,
            "status": "queued",
            "stage": STAGES[0],
            "checkpoints": {},
            "available_at": now,
            "created_at": now,
        },
    )


def claim(
    connection: Connection,
    owner: str,
    now: datetime,
    *,
    concurrency: int = 1,
    lease_seconds: int = 120,
    maximum_attempts: int = 3,
) -> dict[str, Any] | None:
    now = utc(now)
    if concurrency < 1 or lease_seconds < 1 or maximum_attempts < 1:
        raise ValueError("positive concurrency and lease required")
    connection.execute(select(func.pg_advisory_xact_lock(QUEUE_LOCK)))
    # Repeated process deaths must not create an unlimited lease-recovery loop.
    exhausted = connection.execute(
        select(s.jobs.c.id, s.jobs.c.run_id, s.jobs.c.checkpoints)
        .where(
            s.jobs.c.attempts >= maximum_attempts,
            or_(
                s.jobs.c.status == "queued",
                (s.jobs.c.status == "running") & (s.jobs.c.lease_until <= now),
            ),
        )
        .with_for_update(skip_locked=True)
    ).all()
    for old in exhausted:
        finish_failed_requests(connection, old.run_id, now)
        connection.execute(
            update(s.jobs)
            .where(s.jobs.c.id == old.id)
            .values(
                status="failed", error_code="attempts_exhausted", lease_owner=None, lease_until=None
            )
        )
        connection.execute(
            update(s.analysis_runs)
            .where(s.analysis_runs.c.id == old.run_id)
            .values(status="partial" if old.checkpoints else "failed", finished_at=now)
        )
    active = connection.execute(
        select(func.count())
        .select_from(s.jobs)
        .where(s.jobs.c.status == "running", s.jobs.c.lease_until > now)
    ).scalar_one()
    if active >= concurrency:
        return None
    job = (
        connection.execute(
            select(s.jobs)
            .where(
                or_(
                    s.jobs.c.status == "queued",
                    (s.jobs.c.status == "running") & (s.jobs.c.lease_until <= now),
                ),
                s.jobs.c.available_at <= now,
            )
            .order_by(s.jobs.c.available_at, s.jobs.c.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        .mappings()
        .first()
    )
    if job is None:
        return None
    updates = {
        "status": "running",
        "lease_owner": owner,
        "lease_until": now + timedelta(seconds=lease_seconds),
        "heartbeat_at": now,
        "attempts": job["attempts"] + 1,
        "error_code": None,
    }
    connection.execute(update(s.jobs).where(s.jobs.c.id == job["id"]).values(**updates))
    connection.execute(
        update(s.analysis_runs)
        .where(s.analysis_runs.c.id == job["run_id"])
        .values(status="running", finished_at=None)
    )
    return dict(job) | updates


def owned_job(connection: Connection, job_id: UUID, owner: str, now: datetime) -> dict[str, Any]:
    row = (
        connection.execute(
            select(s.jobs)
            .where(
                s.jobs.c.id == job_id,
                s.jobs.c.status == "running",
                s.jobs.c.lease_owner == owner,
                s.jobs.c.lease_until > now,
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if row is None:
        raise ProviderError("lease_lost")
    return dict(row)


def heartbeat(
    connection: Connection, job_id: UUID, owner: str, now: datetime, lease_seconds: int = 120
) -> None:
    owned_job(connection, job_id, owner, now)
    connection.execute(
        update(s.jobs)
        .where(s.jobs.c.id == job_id)
        .values(heartbeat_at=now, lease_until=now + timedelta(seconds=lease_seconds))
    )


def confirm_stage(
    connection: Connection,
    job_id: UUID,
    owner: str,
    now: datetime,
    stage: str,
    checkpoint: dict[str, Any],
    *,
    partial: bool = False,
) -> None:
    job = owned_job(connection, job_id, owner, now)
    if stage != job["stage"]:
        raise ProviderError("stage_conflict")
    checkpoints = dict(job["checkpoints"]) | {stage: checkpoint}
    final = stage == STAGES[-1]
    connection.execute(
        update(s.jobs)
        .where(s.jobs.c.id == job_id)
        .values(
            checkpoints=checkpoints,
            stage="done" if final else STAGES[STAGES.index(stage) + 1],
            status=("partial" if partial else "succeeded") if final else "running",
            lease_until=None if final else job["lease_until"],
        )
    )
    if final:
        connection.execute(
            update(s.analysis_runs)
            .where(s.analysis_runs.c.id == job["run_id"])
            .values(status="partial" if partial else "succeeded", finished_at=now)
        )


def fail_job(
    connection: Connection,
    job_id: UUID,
    owner: str,
    now: datetime,
    error: ProviderError,
    *,
    jitter_seconds: float | None = None,
    maximum_attempts: int = 3,
) -> None:
    if maximum_attempts < 1:
        raise ValueError("positive retry limit required")
    job = owned_job(connection, job_id, owner, now)
    blocked = error.code in BLOCKED_ERRORS or error.may_have_charged
    safe = error.retry_safe and not blocked
    retry = safe and job["attempts"] < maximum_attempts
    status = "queued" if retry else "deferred" if blocked else "failed"
    if not retry:
        finish_failed_requests(connection, job["run_id"], now)
    jitter = SystemRandom().uniform(0, 30) if jitter_seconds is None else jitter_seconds
    delay = min(3600, 30 * 2 ** min(7, max(0, job["attempts"] - 1))) + max(0, min(jitter, 30))
    connection.execute(
        update(s.jobs)
        .where(s.jobs.c.id == job_id)
        .values(
            status=status,
            error_code=error.code,
            lease_owner=None,
            lease_until=None,
            available_at=now + timedelta(seconds=delay) if retry else now,
        )
    )
    connection.execute(
        update(s.analysis_runs)
        .where(s.analysis_runs.c.id == job["run_id"])
        .values(
            status="queued" if retry else "partial" if job["checkpoints"] else status,
            finished_at=None if retry else now,
        )
    )


def create_schedule(
    connection: Connection,
    profile_id: UUID,
    now: datetime,
    configuration: dict[str, Any],
    interval_seconds: int = 3600,
) -> None:
    now = utc(now)
    if interval_seconds < 1:
        raise ValueError("positive schedule interval required")
    connection.execute(
        insert(s.radar_schedules)
        .values(
            profile_id=profile_id,
            schedule_key="radar",
            interval_seconds=interval_seconds,
            paused=True,
            next_due_at=now,
            configuration=configuration,
        )
        .on_conflict_do_nothing(index_elements=["schedule_key"])
    )


def schedule_attention(connection: Connection, schedule: Any) -> UUID | None:
    attention = (
        select(s.jobs.c.id)
        .join(s.analysis_runs, s.analysis_runs.c.id == s.jobs.c.run_id)
        .where(
            s.jobs.c.occurrence_key.startswith(str(schedule["id"]) + ":", autoescape=True),
            s.jobs.c.status.in_(["deferred", "failed"]),
            s.jobs.c.error_code.in_(ATTENTION_ERRORS),
        )
    )
    resumed = schedule["configuration"].get("retry_authorized_after")
    if resumed:
        attention = attention.where(
            s.analysis_runs.c.finished_at >= datetime.fromisoformat(resumed)
        )
    result: UUID | None = connection.execute(attention.limit(1)).scalar_one_or_none()
    return result


def schedule_due(
    connection: Connection, now: datetime, *, globally_paused: bool = True
) -> list[UUID]:
    now = utc(now)
    if globally_paused:
        return []
    connection.execute(select(func.pg_advisory_xact_lock(QUEUE_LOCK)))
    due = (
        connection.execute(
            select(s.radar_schedules)
            .where(s.radar_schedules.c.paused.is_(False), s.radar_schedules.c.next_due_at <= now)
            .with_for_update()
        )
        .mappings()
        .all()
    )
    jobs = []
    for schedule in due:
        needs_attention = schedule_attention(connection, schedule)
        outstanding = connection.execute(
            select(s.jobs.c.id)
            .where(
                s.jobs.c.occurrence_key.startswith(str(schedule["id"]) + ":", autoescape=True),
                s.jobs.c.status.in_(["queued", "running"]),
            )
            .limit(1)
        ).first()
        # Coalesce every missed interval into one occurrence, preserving the original due key.
        if outstanding is None and needs_attention is None:
            jobs.append(
                enqueue(
                    connection,
                    schedule["profile_id"],
                    f"{schedule['id']}:{schedule['next_due_at'].isoformat()}",
                    now,
                    schedule["configuration"],
                    trigger="scheduled",
                    mode=schedule["configuration"].get("mode", "synthetic"),
                )
            )
        elapsed = (now - schedule["next_due_at"]).total_seconds()
        intervals = int(elapsed // schedule["interval_seconds"]) + 1
        next_due = schedule["next_due_at"] + timedelta(
            seconds=intervals * schedule["interval_seconds"]
        )
        connection.execute(
            update(s.radar_schedules)
            .where(s.radar_schedules.c.id == schedule["id"])
            .values(next_due_at=next_due)
        )
    return jobs
