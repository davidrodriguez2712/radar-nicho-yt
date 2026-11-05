"""Cola de solicitudes de propuesta de subnicho: la API valida y encola, el worker las atiende."""

from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Connection
from sqlalchemy.dialects.postgresql import insert as pg_insert

from nicheradar.repositories.schema import subniche_proposal_requests as requests
from nicheradar.subniche_discovery.contracts import ORIGINS
from nicheradar.subniche_discovery.inputs import parse_input
from nicheradar.subniche_discovery.intake import ManualFields

MAX_INPUT = 500
MAX_ERROR_CODE = 80
_LIMIT_LOCK = 7_302_201  # serializa «contar + insertar» para que el tope no se rebase en carrera
_PUBLIC = [column for column in requests.c if column.name != "idempotency_key"]


class ProposalRejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _existing(conn: Connection, key: str) -> UUID | None:
    return conn.execute(
        sa.select(requests.c.id).where(requests.c.idempotency_key == key)
    ).scalar_one_or_none()


def enqueue(
    conn: Connection,
    raw: str,
    *,
    manual: ManualFields | None,
    origin: str,
    key: str,
    now: datetime,
    per_day: int,
) -> tuple[UUID, bool]:
    if origin not in ORIGINS or len(raw) > MAX_INPUT or "\x00" in raw:
        raise ProposalRejected("invalid_input")
    try:
        parsed = parse_input(raw)
    except ValueError:
        raise ProposalRejected("invalid_input") from None
    if parsed.kind == "tweet":
        raise ProposalRejected("tweet_not_supported_yet")
    if manual is not None and parsed.kind != "query":
        raise ProposalRejected("manual_needs_a_query")
    if (found := _existing(conn, key)) is not None:
        return found, False
    conn.execute(sa.select(sa.func.pg_advisory_xact_lock(_LIMIT_LOCK)))
    if (found := _existing(conn, key)) is not None:  # otra petición ganó la carrera
        return found, False
    recent = conn.execute(
        sa.select(sa.func.count())
        .select_from(requests)
        .where(requests.c.created_at > now - timedelta(hours=24))
    ).scalar_one()
    if recent >= per_day:
        raise ProposalRejected("daily_limit")
    request_id = uuid4()
    conn.execute(
        pg_insert(requests)
        .values(
            id=request_id,
            idempotency_key=key,
            input_text=raw.strip(),
            kind=parsed.kind,
            manual=asdict(manual) if manual is not None else None,
            origin=origin,
            status="queued",
            created_at=now,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
    )
    stored = _existing(conn, key)
    assert stored is not None
    return stored, stored == request_id


def _public(row: Any) -> dict[str, Any]:
    return dict(row._mapping)


def claim_next(conn: Connection, now: datetime) -> dict[str, Any] | None:
    next_id = conn.execute(
        sa.select(requests.c.id)
        .where(requests.c.status == "queued")
        .order_by(requests.c.created_at, requests.c.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if next_id is None:
        return None
    row = conn.execute(
        sa.update(requests)
        .where(requests.c.id == next_id)
        .values(status="running", started_at=now)
        .returning(*_PUBLIC)
    ).one()
    return _public(row)


def release_stale(conn: Connection, now: datetime, *, minutes: int = 30) -> int:
    result = conn.execute(
        sa.update(requests)
        .where(
            requests.c.status == "running", requests.c.started_at < now - timedelta(minutes=minutes)
        )
        .values(status="failed", error_code="abandoned", finished_at=now)
    )
    return result.rowcount


def finish_ready(conn: Connection, request_id: UUID, slug: str, now: datetime) -> None:
    conn.execute(
        sa.update(requests)
        .where(requests.c.id == request_id)
        .values(status="ready", hypothesis_slug=slug, error_code=None, finished_at=now)
    )


def finish_failed(conn: Connection, request_id: UUID, code: str, now: datetime) -> None:
    conn.execute(
        sa.update(requests)
        .where(requests.c.id == request_id)
        .values(status="failed", error_code=code[:MAX_ERROR_CODE], finished_at=now)
    )


def get_request(conn: Connection, request_id: UUID) -> dict[str, Any] | None:
    row = conn.execute(sa.select(*_PUBLIC).where(requests.c.id == request_id)).first()
    return _public(row) if row is not None else None


def list_requests(conn: Connection, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        sa.select(*_PUBLIC)
        .order_by(requests.c.created_at.desc(), requests.c.id.desc())
        .limit(limit)
    )
    return [_public(row) for row in rows]
