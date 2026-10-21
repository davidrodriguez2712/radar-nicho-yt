# src/nicheradar/flow_research/service.py
"""Request lifecycle: the app orders research, a Claude Code session claims and answers it."""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, select, update
from sqlalchemy.exc import IntegrityError

from nicheradar.flow_research.evidence import REASONS, build_evidence, ineligible_reason
from nicheradar.market_intel.ingest import LISTING_RETENTION
from nicheradar.market_intel.niches import niche_detail
from nicheradar.repositories.schema import flow_research_dossiers as dossiers
from nicheradar.repositories.schema import flow_research_requests as requests

LEASE = timedelta(minutes=60)
MAX_REJECTIONS = 2
RETENTION = LISTING_RETENTION
ACTIVE = ("pendiente", "en_curso")
SUMMARY = (
    "id",
    "niche_label",
    "format",
    "status",
    "attempts",
    "lease_until",
    "rejection",
    "created_at",
    "updated_at",
)
MESSAGES = REASONS | {
    "not_found": "Encargo o nicho no encontrado.",
    "not_claimable": "El encargo no está pendiente.",
    "lease_lost": "El encargo ya no está reclamado por este investigador.",
}


class FlowResearchError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(MESSAGES[code])
        self.code = code


def _summary(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in SUMMARY}


def release_expired(connection: Connection, now: datetime) -> int:
    """A claimed request whose lease ran out goes back to the queue."""
    result = connection.execute(
        update(requests)
        .where(requests.c.status == "en_curso", requests.c.lease_until <= now)
        .values(status="pendiente", lease_owner=None, lease_until=None, updated_at=now)
    )
    return result.rowcount


def _active(connection: Connection, niche_label: str, format: str) -> UUID | None:
    return connection.execute(
        select(requests.c.id).where(
            requests.c.niche_label == niche_label,
            requests.c.format == format,
            requests.c.status.in_(ACTIVE),
        )
    ).scalar_one_or_none()


def _stored(connection: Connection, request_id: UUID) -> dict[str, Any]:
    row = get_request(connection, request_id)
    assert row is not None
    return row


def create_request(
    connection: Connection, niche_label: str, format: str, now: datetime, timezone: str = "UTC"
) -> tuple[dict[str, Any], bool]:
    """Return ``(request, created)``; an active request is returned, never duplicated."""
    release_expired(connection, now)
    existing = _active(connection, niche_label, format)
    if existing is not None:
        return _stored(connection, existing), False
    detail = niche_detail(connection, niche_label, format, now, timezone)
    if detail is None:
        raise FlowResearchError("not_found")
    reason = ineligible_reason(detail["niche"])
    if reason is not None:
        raise FlowResearchError(reason)
    request_id = uuid4()
    try:
        with connection.begin_nested():
            connection.execute(
                requests.insert().values(
                    id=request_id,
                    niche_label=niche_label,
                    format=format,
                    status="pendiente",
                    evidence=build_evidence(detail),
                    attempts=0,
                    created_at=now,
                    updated_at=now,
                    retain_until=now + RETENTION,
                )
            )
    except IntegrityError:
        # A concurrent creation won the unique index for this niche; return that one.
        winner = _active(connection, niche_label, format)
        if winner is None:
            raise
        return _stored(connection, winner), False
    return _stored(connection, request_id), True


def pending_requests(connection: Connection, now: datetime) -> list[dict[str, Any]]:
    release_expired(connection, now)
    rows = connection.execute(
        select(requests).where(requests.c.status == "pendiente").order_by(requests.c.created_at)
    ).mappings()
    return [_summary(row) for row in rows]


def list_requests(
    connection: Connection,
    *,
    niche_label: str | None = None,
    format: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    query = select(requests).order_by(requests.c.created_at.desc()).limit(limit)
    if niche_label is not None:
        query = query.where(requests.c.niche_label == niche_label)
    if format is not None:
        query = query.where(requests.c.format == format)
    if status is not None:
        query = query.where(requests.c.status == status)
    return [_summary(row) for row in connection.execute(query).mappings()]


def get_request(connection: Connection, request_id: UUID) -> dict[str, Any] | None:
    row = (
        connection.execute(select(requests).where(requests.c.id == request_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    dossier = connection.execute(
        select(dossiers.c.content, dossiers.c.created_at).where(dossiers.c.request_id == request_id)
    ).one_or_none()
    return _summary(row) | {
        "evidence": row["evidence"],
        "dossier": dossier.content if dossier else None,
        "dossier_created_at": dossier.created_at if dossier else None,
    }


def _locked(connection: Connection, request_id: UUID) -> Any:
    row = (
        connection.execute(select(requests).where(requests.c.id == request_id).with_for_update())
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise FlowResearchError("not_found")
    return row


def claim_request(
    connection: Connection, request_id: UUID, owner: str, now: datetime
) -> dict[str, Any]:
    release_expired(connection, now)
    row = _locked(connection, request_id)
    if row["status"] != "pendiente":
        raise FlowResearchError("not_claimable")
    connection.execute(
        update(requests)
        .where(requests.c.id == request_id)
        .values(status="en_curso", lease_owner=owner, lease_until=now + LEASE, updated_at=now)
    )
    return _stored(connection, request_id)
