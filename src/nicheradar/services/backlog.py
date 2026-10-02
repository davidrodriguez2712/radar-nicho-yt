from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import Connection, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from nicheradar.domain.profile import VideoFormat
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import ConflictError, insert_record

ReviewState = Literal["new", "watching", "selected", "dismissed"]


def opportunity_identity(
    connection: Connection, topic_id: UUID, audience_key: str, language: str, format: VideoFormat
) -> UUID:
    identity = {
        "topic_id": topic_id,
        "audience_key": audience_key,
        "language": language,
        "format": format.value,
    }
    connection.execute(
        pg_insert(s.opportunities)
        .values(**identity)
        .on_conflict_do_nothing(index_elements=["topic_id", "audience_key", "language", "format"])
    )
    result: UUID = connection.execute(
        select(s.opportunities.c.id).where(
            *(s.opportunities.c[key] == value for key, value in identity.items())
        )
    ).scalar_one()
    return result


def latest_decision(connection: Connection, opportunity_id: UUID) -> dict[str, Any]:
    row = (
        connection.execute(
            select(s.opportunity_decisions)
            .where(s.opportunity_decisions.c.opportunity_id == opportunity_id)
            .order_by(s.opportunity_decisions.c.version.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    return dict(row) if row else {"state": "new", "version": 0, "note": ""}


def decide(
    connection: Connection,
    opportunity_id: UUID,
    state: ReviewState,
    note: str,
    expected_version: int,
    now: datetime,
) -> dict[str, Any]:
    connection.execute(
        select(s.opportunities.c.id).where(s.opportunities.c.id == opportunity_id).with_for_update()
    ).scalar_one()
    previous = latest_decision(connection, opportunity_id)
    if previous["version"] != expected_version:
        raise ConflictError("decision version changed")
    connection.execute(
        insert(s.opportunity_decisions).values(
            opportunity_id=opportunity_id,
            state=state,
            note=note,
            version=expected_version + 1,
            created_at=now,
        )
    )
    return latest_decision(connection, opportunity_id)


def append_evaluation(connection: Connection, opportunity_id: UUID, values: dict[str, Any]) -> UUID:
    connection.execute(
        select(s.opportunities.c.id).where(s.opportunities.c.id == opportunity_id).with_for_update()
    ).scalar_one()
    version = (
        connection.execute(
            select(func.coalesce(func.max(s.evaluation_versions.c.version), 0)).where(
                s.evaluation_versions.c.opportunity_id == opportunity_id
            )
        ).scalar_one()
        + 1
    )
    return insert_record(
        connection,
        "evaluation_versions",
        values | {"opportunity_id": opportunity_id, "version": version},
    )


def describe_change(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
    previous_rank: int | None = None,
    current_rank: int | None = None,
) -> list[str]:
    if previous is None:
        return ["first_evaluation"]
    changes = []
    if previous.get("method_version") != current.get("method_version") or previous.get(
        "reference_version"
    ) != current.get("reference_version"):
        changes.append("method_changed")
    comparable = "method_changed" not in changes
    if comparable and any(
        previous.get(key) != current.get(key)
        for key in ("market_score", "creator_fit", "final_score", "features")
    ):
        changes.append("evidence_or_assumptions_changed")
    if previous_rank is not None and current_rank is not None and previous_rank != current_rank:
        changes.append("relative_rank_changed")
    return changes or ["unchanged"]
