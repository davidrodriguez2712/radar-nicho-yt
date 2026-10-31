# src/nicheradar/subniche_discovery/store.py
"""Lifecycle of sub-niche hypotheses: proposed -> active -> paused | archived."""

import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, and_, or_, select, update

from nicheradar.repositories.schema import hypothesis_seed_channels as seeds
from nicheradar.repositories.schema import niche_hypotheses as nh
from nicheradar.subniche_discovery.contracts import HypothesisDraft

_ALLOWED = {
    "proposed": {"archived"},
    "active": {"paused", "archived"},
    "paused": {"active", "archived"},
    "archived": set(),
}


class DuplicateHypothesis(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InvalidTransition(Exception):
    pass


class UnknownHypothesis(Exception):
    pass


def unique_slug(connection: Connection, base: str) -> str:
    taken = set(connection.execute(select(nh.c.slug)).scalars())
    if base not in taken:
        return base
    for suffix in range(2, 50):
        candidate = f"{base[:55]}_{suffix}"
        if candidate not in taken:
            return candidate
    raise DuplicateHypothesis("slug")


def create_proposed(connection: Connection, draft: HypothesisDraft, now: datetime) -> UUID:
    if connection.execute(select(nh.c.id).where(nh.c.slug == draft.slug)).first():
        raise DuplicateHypothesis("slug")
    live = connection.execute(select(nh.c.queries).where(nh.c.status != "archived")).scalars()
    taken = {query for queries in live for query in queries}
    clash = sorted(set(draft.queries) & taken)
    if clash:
        raise DuplicateHypothesis(f"query:{clash[0]}")
    if draft.seed_channel_ids:
        used = connection.execute(
            select(seeds.c.channel_id)
            .join(nh, nh.c.id == seeds.c.hypothesis_id)
            .where(nh.c.status != "archived", seeds.c.channel_id.in_(draft.seed_channel_ids))
        ).scalar()
        if used:
            raise DuplicateHypothesis(f"seed_channel:{used}")
    hypothesis_id = uuid4()
    connection.execute(
        nh.insert().values(
            id=hypothesis_id,
            slug=draft.slug,
            label=draft.label,
            family=draft.family,
            parent_niche_slug=draft.parent_niche_slug,
            queries=list(draft.queries),
            origin=draft.origin,
            status="proposed",
            source_input=draft.source_input,
            created_at=now,
        )
    )
    for channel_id in draft.seed_channel_ids:
        connection.execute(
            seeds.insert().values(hypothesis_id=hypothesis_id, channel_id=channel_id, added_at=now)
        )
    return hypothesis_id


def _row(connection: Connection, slug: str) -> dict[str, Any]:
    row = (
        connection.execute(select(nh).where(nh.c.slug == slug).with_for_update()).mappings().first()
    )
    if row is None:
        raise UnknownHypothesis(slug)
    return dict(row)


def get_hypothesis(connection: Connection, slug: str) -> dict[str, Any]:
    row = _row(connection, slug)
    row["seed_channels"] = list(
        connection.execute(
            select(seeds.c.channel_id)
            .where(seeds.c.hypothesis_id == row["id"])
            .order_by(seeds.c.channel_id)
        ).scalars()
    )
    return row


def approve(connection: Connection, slug: str, now: datetime) -> None:
    row = _row(connection, slug)
    if row["status"] != "proposed":
        raise InvalidTransition(f"{slug} is {row['status']}, only proposed can be approved")
    connection.execute(
        update(nh).where(nh.c.id == row["id"]).values(status="active", approved_at=now)
    )


def set_status(connection: Connection, slug: str, status: str) -> None:
    row = _row(connection, slug)
    if status not in _ALLOWED[row["status"]]:
        raise InvalidTransition(f"{slug}: {row['status']} -> {status} is not allowed")
    values: dict[str, Any] = {"status": status}
    if status == "archived":
        values["finalist"] = False
    connection.execute(update(nh).where(nh.c.id == row["id"]).values(**values))


def set_finalist(connection: Connection, slug: str, value: bool) -> None:
    row = _row(connection, slug)
    if row["status"] != "active":
        raise InvalidTransition(f"{slug} must be active to be a finalist")
    connection.execute(update(nh).where(nh.c.id == row["id"]).values(finalist=value))


def request_remeasure(connection: Connection, slug: str) -> None:
    row = _row(connection, slug)
    if row["status"] != "active":
        raise InvalidTransition(f"{slug} must be active to be measured")
    connection.execute(update(nh).where(nh.c.id == row["id"]).values(last_measured_at=None))


def list_hypotheses(connection: Connection, status: str | None = None) -> list[dict[str, Any]]:
    query = select(nh).order_by(nh.c.created_at, nh.c.slug)
    if status is not None:
        query = query.where(nh.c.status == status)
    return [dict(row) for row in connection.execute(query).mappings()]


def due_hypotheses(
    connection: Connection, now: datetime, *, refresh_days: int = 7
) -> list[dict[str, Any]]:
    stale = now - timedelta(days=refresh_days)
    rows = connection.execute(
        select(nh.c.slug)
        .where(
            nh.c.status == "active",
            or_(
                nh.c.last_measured_at.is_(None),
                and_(nh.c.finalist.is_(True), nh.c.last_measured_at < stale),
            ),
        )
        .order_by(nh.c.approved_at, nh.c.slug)
    ).scalars()
    return [get_hypothesis(connection, slug) for slug in rows]


def mark_measured(connection: Connection, hypothesis_id: UUID, now: datetime) -> None:
    connection.execute(update(nh).where(nh.c.id == hypothesis_id).values(last_measured_at=now))


def export_yaml(connection: Connection) -> str:
    """JSON scalars are valid YAML, so no YAML dependency is needed."""
    lines: list[str] = []
    for row in list_hypotheses(connection):
        full = get_hypothesis(connection, row["slug"])
        lines += [
            f"- slug: {json.dumps(full['slug'])}",
            f"  label: {json.dumps(full['label'])}",
            f"  family: {json.dumps(full['family'])}",
            f"  parent_niche: {json.dumps(full['parent_niche_slug'])}",
            f"  queries: {json.dumps(full['queries'])}",
            f"  origin: {json.dumps(full['origin'])}",
            f"  status: {json.dumps(full['status'])}",
            f"  finalist: {json.dumps(full['finalist'])}",
            f"  seed_channels: {json.dumps(full['seed_channels'])}",
        ]
    return "\n".join(lines) + ("\n" if lines else "")
