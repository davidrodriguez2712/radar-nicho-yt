# src/nicheradar/flow_research/service.py
"""Request lifecycle: the app orders research, a Claude Code session claims and answers it."""

import re
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, select, update
from sqlalchemy.exc import IntegrityError

from nicheradar.flow_research import gates as gate_rules
from nicheradar.flow_research.contracts import (
    SCHEMA_VERSION,
    DossierV2,
    Problem,
    human_minutes_per_video,
    validate_dossier,
)
from nicheradar.flow_research.evidence import REASONS, build_evidence, ineligible_reason
from nicheradar.flow_research.gates import (
    GateReason,
    Gates,
    describe,
    minutes_reasons,
    niche_reasons,
)
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
    "language",
    "status",
    "attempts",
    "lease_until",
    "rejection",
    "created_at",
    "updated_at",
)
LANGUAGE = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")
MESSAGES = REASONS | {
    "invalid_language": "El idioma debe ser un código como en o es; «unknown» no se investiga.",
    "gate_failed": "El nicho no pasa las compuertas de selección.",
    "not_found": "Encargo o nicho no encontrado.",
    "not_claimable": "El encargo no está pendiente.",
    "lease_lost": "El encargo ya no está reclamado por este investigador.",
}


class FlowResearchError(Exception):
    def __init__(self, code: str, reasons: list[GateReason] | None = None) -> None:
        super().__init__(MESSAGES[code])
        self.code = code
        self.reasons = reasons or []


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


def _active(connection: Connection, niche_label: str, format: str, language: str) -> UUID | None:
    return connection.execute(
        select(requests.c.id).where(
            requests.c.niche_label == niche_label,
            requests.c.format == format,
            requests.c.language == language,
            requests.c.status.in_(ACTIVE),
        )
    ).scalar_one_or_none()


def _stored(connection: Connection, request_id: UUID) -> dict[str, Any]:
    row = get_request(connection, request_id)
    assert row is not None
    return row


def create_request(
    connection: Connection,
    niche_label: str,
    format: str,
    language: str,
    now: datetime,
    timezone: str = "UTC",
    *,
    gates: Gates | None = None,
    gate_override: dict[str, str] | None = None,
) -> tuple[dict[str, Any], bool]:
    """Return ``(request, created)``; an active request is returned, never duplicated.

    The selection gates (automation, policy risk) stop a niche before any research is ordered;
    ``gate_override`` (``reason`` and ``by``, chosen by a human) lets it through and is frozen in
    the evidence with its time. An unknown automation score does not fail the gate.

    The key is niche + format + language: the same niche researched in two languages is two
    markets, each with its own competitors, prices and tools.
    """
    if not LANGUAGE.fullmatch(language):
        raise FlowResearchError("invalid_language")
    release_expired(connection, now)
    existing = _active(connection, niche_label, format, language)
    if existing is not None:
        return _stored(connection, existing), False
    detail = niche_detail(connection, niche_label, format, now, timezone)
    if detail is None:
        raise FlowResearchError("not_found")
    reason = ineligible_reason(detail["niche"])
    if reason is not None:
        raise FlowResearchError(reason)
    gates = gates or gate_rules.DEFAULT_GATES
    failing = niche_reasons(detail["niche"], gates)
    if failing and gate_override is None:
        raise FlowResearchError("gate_failed", failing)
    override = None
    if failing and gate_override is not None:
        override = {**gate_override, "at": now.isoformat()}
    request_id = uuid4()
    try:
        with connection.begin_nested():
            connection.execute(
                requests.insert().values(
                    id=request_id,
                    niche_label=niche_label,
                    format=format,
                    language=language,
                    status="pendiente",
                    evidence=build_evidence(detail, language, gates, override),
                    attempts=0,
                    created_at=now,
                    updated_at=now,
                    retain_until=now + RETENTION,
                )
            )
    except IntegrityError:
        # A concurrent creation won the unique index for this niche; return that one.
        winner = _active(connection, niche_label, format, language)
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
    language: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    query = select(requests).order_by(requests.c.created_at.desc()).limit(limit)
    if niche_label is not None:
        query = query.where(requests.c.niche_label == niche_label)
    if format is not None:
        query = query.where(requests.c.format == format)
    if language is not None:
        query = query.where(requests.c.language == language)
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
    holder = f"{owner[:60]}#{uuid4().hex}"
    connection.execute(
        update(requests)
        .where(requests.c.id == request_id)
        .values(status="en_curso", lease_owner=holder, lease_until=now + LEASE, updated_at=now)
    )
    # The label is client-chosen text; the suffix makes every claim distinct, so a stale
    # session that reused the same label can never submit into a newer claim.
    return _stored(connection, request_id) | {"lease_owner": holder}


def _gate_problems(dossier: DossierV2, row: Any, gates: Gates) -> list[Problem]:
    """A dossier that recommends going ahead must pass the gates, unless a human overrode them.

    ``no_go`` is always acceptable. Blocked rights are not overridable (contract-level check).
    """
    if dossier.verdict.recommendation == "no_go":
        return []
    evidence = row["evidence"]
    reasons: list[GateReason] = []
    if "gate_override" not in evidence:
        reasons += niche_reasons(evidence["niche"], gates)
        reasons += minutes_reasons(human_minutes_per_video(dossier), gates)
    if not reasons:
        return []
    return [
        {
            "path": "verdict.recommendation",
            "message": f"{describe(reasons)} Entrega no_go o pide una excepción al propietario.",
        }
    ]


def _request_problems(dossier: DossierV2, row: Any, gates: Gates) -> list[Problem]:
    """Checks that need the request: the dossier must answer exactly what was ordered."""
    problems: list[Problem] = _gate_problems(dossier, row, gates)
    if dossier.request_id != row["id"]:
        problems.append({"path": "request_id", "message": "no corresponde a este encargo"})
    if dossier.niche_label != row["niche_label"]:
        problems.append({"path": "niche_label", "message": "no corresponde al nicho del encargo"})
    if dossier.format != row["format"]:
        problems.append({"path": "format", "message": "no corresponde al formato del encargo"})
    if dossier.language != row["language"]:
        problems.append({"path": "language", "message": "no corresponde al idioma del encargo"})
    if row["evidence"]["niche"].get("confidence") == "baja" and not dossier.verdict.unknowns:
        problems.append(
            {
                "path": "verdict.unknowns",
                "message": "la confianza del nicho es baja: declara qué no se pudo verificar",
            }
        )
    return problems


def submit_dossier(
    connection: Connection,
    request_id: UUID,
    owner: str,
    payload: object,
    now: datetime,
    gates: Gates | None = None,
) -> dict[str, Any]:
    release_expired(connection, now)
    row = _locked(connection, request_id)
    if row["status"] != "en_curso" or row["lease_owner"] != owner or row["lease_until"] <= now:
        raise FlowResearchError("lease_lost")
    dossier, problems = validate_dossier(payload, now)
    if dossier is not None:
        problems = _request_problems(dossier, row, gates or gate_rules.DEFAULT_GATES)
    if dossier is None or problems:
        attempts = row["attempts"] + 1
        rejected = attempts >= MAX_REJECTIONS
        connection.execute(
            update(requests)
            .where(requests.c.id == request_id)
            .values(
                attempts=attempts,
                status="rechazado" if rejected else "en_curso",
                rejection={"problems": problems, "at": now.isoformat()},
                lease_owner=None if rejected else row["lease_owner"],
                lease_until=None if rejected else row["lease_until"],
                updated_at=now,
            )
        )
        return {
            "accepted": False,
            "status": "rechazado" if rejected else "en_curso",
            "problems": problems,
            "remaining_attempts": max(0, MAX_REJECTIONS - attempts),
        }
    dossier_id = uuid4()
    retain_until = now + RETENTION
    connection.execute(
        dossiers.insert().values(
            id=dossier_id,
            request_id=request_id,
            niche_label=row["niche_label"],
            format=row["format"],
            language=row["language"],
            schema_version=SCHEMA_VERSION,
            content=dossier.model_dump(mode="json"),
            created_at=now,
            retain_until=retain_until,
        )
    )
    connection.execute(
        update(requests)
        .where(requests.c.id == request_id)
        .values(
            status="listo",
            lease_owner=None,
            lease_until=None,
            rejection=None,
            retain_until=retain_until,
            updated_at=now,
        )
    )
    return {"accepted": True, "status": "listo", "dossier_id": dossier_id}
