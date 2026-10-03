"""Persistence for saved channel-analysis reports; mirrors services/console.py's
pagination shape. One row per run — re-analyzing creates a new run and a new row."""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Connection

from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.schema import channel_analyses
from nicheradar.services.channel_analysis_scoring import compute_score


def run_consumption(connection: Connection, run_id: UUID) -> dict[str, Any]:
    """Real spend for one run, using the same accounting split as the jobs view
    (services/operations.py::jobs): `confirmed` is settled spend from the cost ledger;
    `reservations` are still-open liabilities (`reserved`, or sent with an unproven
    charge, `unknown_charge`). Released (certified never sent) reservations are neither."""
    confirmed = connection.execute(
        select(s.cost_ledger.c.unit, func.sum(s.cost_ledger.c.amount).label("amount"))
        .join(s.provider_requests, s.provider_requests.c.id == s.cost_ledger.c.request_id)
        .where(s.provider_requests.c.run_id == run_id)
        .group_by(s.cost_ledger.c.unit)
        .order_by(s.cost_ledger.c.unit)
    ).all()
    open_reservations = connection.execute(
        select(
            s.cost_reservations.c.unit,
            s.cost_reservations.c.status,
            func.sum(s.cost_reservations.c.amount).label("amount"),
        )
        .join(s.provider_requests, s.provider_requests.c.id == s.cost_reservations.c.request_id)
        .where(
            s.provider_requests.c.run_id == run_id,
            s.cost_reservations.c.status.in_(["reserved", "unknown_charge"]),
        )
        .group_by(s.cost_reservations.c.unit, s.cost_reservations.c.status)
        .order_by(s.cost_reservations.c.unit, s.cost_reservations.c.status)
    ).all()
    return {
        "confirmed": {row.unit: float(row.amount) for row in confirmed},
        "reservations": [
            {"unit": row.unit, "status": row.status, "amount": float(row.amount)}
            for row in open_reservations
        ],
    }


def save_channel_analysis(
    connection: Connection,
    run_id: UUID,
    profile_id: UUID,
    checkpoints: dict[str, Any],
    now: datetime,
    *,
    status: str = "completed",
    configuration: dict[str, Any] | None = None,
) -> UUID:
    # `status` defaults to "completed" for the normal path, where every earlier stage
    # confirmed cleanly before reaching "persist". The pipeline's channel-analysis flow
    # (Task 13) passes status="partial" explicitly when an earlier stage recorded a
    # budget-exhaustion reason that was carried forward, stage by stage, to this point —
    # confirm_channel_analysis_stage() only honors `partial=True` at the final ("persist")
    # stage, so a mid-sequence budget error must still reach persist to be recorded here.
    # status="failed" is written on a hard failure; the job may still be retried, so a
    # later save for the same run replaces that provisional row instead of duplicating it.
    configuration = configuration or {}
    channel = checkpoints.get("resolve", {}).get("channel", {})
    values = {
        "channel_input": channel.get("title") or configuration.get("channel_input", ""),
        "channel_external_id": channel.get("id"),
        "status": status,
        "configuration": configuration,
        "snapshot": checkpoints,
        "consumption": run_consumption(connection, run_id),
    }
    statement = insert(channel_analyses).values(
        id=uuid4(),
        profile_id=profile_id,
        run_id=run_id,
        created_at=now,
        retain_until=now + timedelta(days=180),
        **values,
    )
    result: UUID = connection.execute(
        statement.on_conflict_do_update(index_elements=["run_id"], set_=values).returning(
            channel_analyses.c.id
        )
    ).scalar_one()
    return result


def _view(row: Any, now: datetime | None) -> dict[str, Any]:
    # Same convention as services/console.py::opportunity_detail: expired rows stay
    # visible, but their retained content is withheld once retention is due, even
    # before the expiry job has physically nulled it.
    view = dict(row)
    available = view["expired_at"] is None and (now is None or view["retain_until"] > now)
    if not available:
        view["snapshot"] = None
    view["evidence_available"] = available
    view["score"] = (
        compute_score(view["snapshot"])
        if view["snapshot"]
        else {"value": None, "components": {}, "components_used": []}
    )
    return view


def list_channel_analyses(
    connection: Connection, *, limit: int = 20, offset: int = 0, now: datetime | None = None
) -> dict[str, Any]:
    total = connection.execute(select(func.count()).select_from(channel_analyses)).scalar_one()
    rows = (
        connection.execute(
            select(channel_analyses)
            .order_by(channel_analyses.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .mappings()
        .all()
    )
    return {
        "items": [_view(row, now) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def channel_analysis_detail(
    connection: Connection, analysis_id: UUID | str, *, now: datetime | None = None
) -> dict[str, Any] | None:
    row = (
        connection.execute(select(channel_analyses).where(channel_analyses.c.id == analysis_id))
        .mappings()
        .first()
    )
    return _view(row, now) if row else None
