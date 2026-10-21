# src/nicheradar/market_intel/runs.py
"""Own schedule and durable run state for the market scraper.

Deliberately separate from radar_schedules/jobs: the radar code assumes a single `radar`
schedule row, `schedule_due()` enqueues a radar job for every unpaused row and `claim()` takes
any queued job, so sharing those tables would couple the two pipelines.
"""

from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, func, select, update
from sqlalchemy.dialects.postgresql import insert

from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import insert_record
from nicheradar.repositories.schema import market_intel_schedule as schedule_table
from nicheradar.repositories.schema import market_scrape_runs as runs

SCHEDULE_KEY = "market_intel_scrape"
INTERVAL_SECONDS = 86_400
STAGES = ("list", "detail", "reconcile", "classify", "verify", "snapshot")
FINISHED = ("succeeded", "partial", "failed", "blocked")
LEASE_SECONDS = 3_600
MAXIMUM_ATTEMPTS = 3
MARKET_LOCK = 724_619_014
_ANALYSIS_STATUS = {
    "succeeded": "succeeded",
    "partial": "partial",
    "failed": "failed",
    "blocked": "failed",
}


class LeaseLost(Exception):
    """This worker no longer owns the run (lease expired or taken over)."""


class StageConflict(Exception):
    """The stage being confirmed is not the run's current stage."""


def local_date(now: datetime, timezone: str) -> date:
    return now.astimezone(ZoneInfo(timezone)).date()


def run_key(now: datetime, timezone: str) -> str:
    """One run per LOCAL day (NR_TIMEZONE), so a UTC date change never splits or skips a day."""
    return f"market_scrape:{local_date(now, timezone).isoformat()}"


def ensure_schedule(connection: Connection, now: datetime) -> None:
    connection.execute(
        insert(schedule_table)
        .values(
            id=uuid4(),
            schedule_key=SCHEDULE_KEY,
            interval_seconds=INTERVAL_SECONDS,
            next_due_at=now,
            configuration={},
        )
        .on_conflict_do_nothing(index_elements=["schedule_key"])
    )


def get_schedule(connection: Connection, *, lock: bool = False) -> dict[str, Any]:
    query = select(schedule_table).where(schedule_table.c.schedule_key == SCHEDULE_KEY)
    if lock:
        query = query.with_for_update()
    return dict(connection.execute(query).mappings().one())


def set_paused(connection: Connection, paused: bool, now: datetime) -> dict[str, Any]:
    ensure_schedule(connection, now)
    values: dict[str, Any] = {"paused": paused}
    if not paused:
        values["next_due_at"] = now
    connection.execute(
        update(schedule_table).where(schedule_table.c.schedule_key == SCHEDULE_KEY).values(**values)
    )
    return get_schedule(connection)


def advance_schedule(connection: Connection, now: datetime) -> None:
    connection.execute(
        update(schedule_table)
        .where(schedule_table.c.schedule_key == SCHEDULE_KEY)
        .values(next_due_at=now + timedelta(seconds=INTERVAL_SECONDS))
    )


def get_run(connection: Connection, run_id: UUID) -> dict[str, Any]:
    return dict(connection.execute(select(runs).where(runs.c.id == run_id)).mappings().one())


def ensure_run(
    connection: Connection, key: str, now: datetime, *, mode: str, profile_id: UUID
) -> UUID:
    connection.execute(select(func.pg_advisory_xact_lock(MARKET_LOCK)))
    existing = connection.execute(
        select(runs.c.id).where(runs.c.run_key == key)
    ).scalar_one_or_none()
    if existing is not None:
        return UUID(str(existing))
    # provider_requests.run_id references analysis_runs: the LLM spend of a scrape needs one.
    analysis_run_id = insert_record(
        connection,
        "analysis_runs",
        {
            "profile_id": profile_id,
            "mode": mode,
            "trigger": "market_scrape",
            "status": "queued",
            "configuration": {"source": "dealbaron"},
        },
    )
    run_id = uuid4()
    connection.execute(
        insert(runs).values(
            id=run_id,
            run_key=key,
            analysis_run_id=analysis_run_id,
            status="queued",
            stage=STAGES[0],
            checkpoints={},
            stats={},
            created_at=now,
        )
    )
    return run_id


def _mirror(
    connection: Connection, analysis_run_id: UUID | None, status: str, now: datetime
) -> None:
    if analysis_run_id is None:
        return
    connection.execute(
        update(s.analysis_runs)
        .where(s.analysis_runs.c.id == analysis_run_id)
        .values(status=status, finished_at=None if status == "running" else now)
    )


def claim_run(
    connection: Connection, run_id: UUID, owner: str, now: datetime
) -> dict[str, Any] | None:
    connection.execute(select(func.pg_advisory_xact_lock(MARKET_LOCK)))
    row = (
        connection.execute(select(runs).where(runs.c.id == run_id).with_for_update())
        .mappings()
        .one()
    )
    if row["status"] in FINISHED:
        return None
    if row["status"] == "running" and row["lease_until"] is not None and row["lease_until"] > now:
        return None
    if row["attempts"] >= MAXIMUM_ATTEMPTS:
        connection.execute(
            update(runs)
            .where(runs.c.id == run_id)
            .values(
                status="failed",
                error_code="attempts_exhausted",
                lease_owner=None,
                lease_until=None,
                finished_at=now,
            )
        )
        _mirror(connection, row["analysis_run_id"], "failed", now)
        return None
    values: dict[str, Any] = {
        "status": "running",
        "lease_owner": owner,
        "lease_until": now + timedelta(seconds=LEASE_SECONDS),
        "attempts": row["attempts"] + 1,
        "error_code": None,
        "started_at": row["started_at"] or now,
    }
    connection.execute(update(runs).where(runs.c.id == run_id).values(**values))
    _mirror(connection, row["analysis_run_id"], "running", now)
    return dict(row) | values


def _owned(connection: Connection, run_id: UUID, owner: str, now: datetime) -> dict[str, Any]:
    row = (
        connection.execute(
            select(runs)
            .where(
                runs.c.id == run_id,
                runs.c.status == "running",
                runs.c.lease_owner == owner,
                runs.c.lease_until > now,
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if row is None:
        raise LeaseLost
    return dict(row)


def advance(
    connection: Connection,
    run_id: UUID,
    owner: str,
    now: datetime,
    stage: str,
    checkpoint: dict[str, Any],
) -> None:
    row = _owned(connection, run_id, owner, now)
    if stage != row["stage"]:
        raise StageConflict(stage)
    position = STAGES.index(stage)
    following = STAGES[position + 1] if position + 1 < len(STAGES) else "done"
    connection.execute(
        update(runs)
        .where(runs.c.id == run_id)
        .values(
            stage=following,
            checkpoints=dict(row["checkpoints"]) | {stage: checkpoint},
            lease_until=now + timedelta(seconds=LEASE_SECONDS),
        )
    )


def finish(
    connection: Connection,
    run_id: UUID,
    owner: str,
    now: datetime,
    *,
    status: str,
    error_code: str | None = None,
    stats: dict[str, Any] | None = None,
) -> None:
    row = _owned(connection, run_id, owner, now)
    connection.execute(
        update(runs)
        .where(runs.c.id == run_id)
        .values(
            status=status,
            error_code=error_code,
            stats=stats if stats is not None else row["stats"],
            lease_owner=None,
            lease_until=None,
            finished_at=now,
        )
    )
    _mirror(connection, row["analysis_run_id"], _ANALYSIS_STATUS[status], now)


def recent_runs(connection: Connection, limit: int = 20) -> list[dict[str, Any]]:
    rows = connection.execute(
        select(runs).order_by(runs.c.created_at.desc()).limit(limit)
    ).mappings()
    return [dict(row) for row in rows]
