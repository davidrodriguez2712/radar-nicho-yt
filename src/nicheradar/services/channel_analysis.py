"""Persistence for saved channel-analysis reports; mirrors services/console.py's
pagination shape. Each row is immutable — re-analyzing creates a new row."""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from nicheradar.repositories.core import insert_record
from nicheradar.repositories.schema import channel_analyses


def save_channel_analysis(
    connection: Connection,
    run_id: UUID,
    profile_id: UUID,
    checkpoints: dict[str, Any],
    now: datetime,
) -> UUID:
    # This is only ever called from the pipeline's final "persist" stage (Task 13), which
    # only runs once every earlier stage has already confirmed cleanly — so the row is
    # "completed" by construction. A stage that hit a budget wall exits via the pipeline's
    # own partial-confirm path (Task 13's except block) and never reaches persist at all;
    # a channel-not-found or similar hard failure never reaches it either (Task 9's
    # ProviderError propagates to the generic fail_job() path instead).
    channel = checkpoints.get("resolve", {}).get("channel", {})
    return insert_record(
        connection,
        "channel_analyses",
        {
            "profile_id": profile_id,
            "run_id": run_id,
            "channel_input": channel.get("title", ""),
            "channel_external_id": channel.get("id"),
            "status": "completed",
            "configuration": {},
            "snapshot": checkpoints,
            "consumption": {},
            "created_at": now,
            "retain_until": now + timedelta(days=180),
        },
    )


def list_channel_analyses(
    connection: Connection, *, limit: int = 20, offset: int = 0
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
    return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def channel_analysis_detail(
    connection: Connection, analysis_id: UUID | str
) -> dict[str, Any] | None:
    row = (
        connection.execute(select(channel_analyses).where(channel_analyses.c.id == analysis_id))
        .mappings()
        .first()
    )
    return dict(row) if row else None
