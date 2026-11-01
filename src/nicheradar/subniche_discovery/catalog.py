# src/nicheradar/subniche_discovery/catalog.py
"""Read model: hypotheses with their latest measurement and research request.

Used by the dashboard, the private API and the research orders. Read-only.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Connection, select

from nicheradar.repositories.schema import discovery_channel_snapshots as channel_snapshots
from nicheradar.repositories.schema import flow_research_requests as requests
from nicheradar.repositories.schema import hypothesis_channel_hits as hits
from nicheradar.repositories.schema import hypothesis_snapshots as snapshots
from nicheradar.repositories.schema import niche_hypotheses as nh

PREFIX = "subniche:"
ACTIVE_STATUSES = ("active", "proposed")
MAX_CHANNELS = 10


def research_label(slug: str) -> str:
    return PREFIX + slug


def slug_of(label: str) -> str | None:
    return label.removeprefix(PREFIX) if label.startswith(PREFIX) else None


def _money(value: Any) -> str | None:
    return None if value is None else f"{value:.2f}"


def _latest_snapshots() -> Any:
    return (
        select(snapshots)
        .distinct(snapshots.c.hypothesis_id)
        .order_by(snapshots.c.hypothesis_id, snapshots.c.measured_at.desc())
        .subquery()
    )


def _measurement(row: Any) -> dict[str, Any] | None:
    if row["measured_at"] is None:
        return None
    profile = row["profile"]
    return {
        "measured_at": row["measured_at"],
        "included": profile.get("channels_included", 0),
        "stable_channels": row["stable_channels"],
        "volatile_channels": profile.get("volatile_channels", 0),
        "traction_channels": row["traction_channels"],
        "large_channels": profile.get("large_channels", 0),
        "excluded": profile.get("excluded", {}),
        "income_low": _money(row["median_income_low"]),
        "income_high": _money(row["median_income_high"]),
        "rpm_source": profile.get("rpm_source"),
        "signal": profile.get("signal"),
    }


def _hypothesis(row: Any) -> dict[str, Any]:
    return {
        "slug": row["slug"],
        "label": row["label"],
        "family": row["family"],
        "parent_niche_slug": row["parent_niche_slug"],
        "status": row["status"],
        "finalist": row["finalist"],
        "language": row["language"],
        "format": row["format"],
        "queries": list(row["queries"]),
    }


def _latest_research(connection: Connection) -> dict[str, dict[str, Any]]:
    query = (
        select(
            requests.c.niche_label,
            requests.c.id,
            requests.c.status,
            requests.c.language,
            requests.c.created_at,
        )
        .where(requests.c.niche_label.like(PREFIX + "%"))
        .order_by(requests.c.created_at.desc())
    )
    latest: dict[str, dict[str, Any]] = {}
    for row in connection.execute(query).mappings():
        latest.setdefault(
            row["niche_label"],
            {
                "id": row["id"],
                "status": row["status"],
                "language": row["language"],
                "created_at": row["created_at"],
            },
        )
    return latest


def _columns(latest: Any) -> list[Any]:
    return [
        nh.c.slug,
        nh.c.label,
        nh.c.family,
        nh.c.parent_niche_slug,
        nh.c.status,
        nh.c.finalist,
        nh.c.language,
        nh.c.format,
        nh.c.queries,
        latest.c.run_id,
        latest.c.measured_at,
        latest.c.stable_channels,
        latest.c.traction_channels,
        latest.c.median_income_low,
        latest.c.median_income_high,
        latest.c.profile,
    ]


def list_subniches(
    connection: Connection, *, include_inactive: bool = False
) -> list[dict[str, Any]]:
    latest = _latest_snapshots()
    query = select(*_columns(latest)).select_from(
        nh.outerjoin(latest, latest.c.hypothesis_id == nh.c.id)
    )
    if not include_inactive:
        query = query.where(nh.c.status.in_(ACTIVE_STATUSES))
    query = query.order_by(
        nh.c.finalist.desc(), latest.c.traction_channels.desc().nulls_last(), nh.c.slug
    )
    research = _latest_research(connection)
    return [
        _hypothesis(row)
        | {
            "measurement": _measurement(row),
            "research": research.get(research_label(row["slug"])),
        }
        for row in connection.execute(query).mappings()
    ]


def subniche_detail(connection: Connection, slug: str, now: datetime) -> dict[str, Any] | None:
    latest = _latest_snapshots()
    row = (
        connection.execute(
            select(*_columns(latest))
            .select_from(nh.outerjoin(latest, latest.c.hypothesis_id == nh.c.id))
            .where(nh.c.slug == slug)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    channels: list[dict[str, Any]] = []
    if row["run_id"] is not None:
        hypothesis_id = connection.execute(select(nh.c.id).where(nh.c.slug == slug)).scalar_one()
        query = (
            select(
                hits.c.channel_id,
                channel_snapshots.c.title,
                hits.c.subscribers,
                hits.c.monthly_long_views,
                hits.c.income_low,
                hits.c.income_high,
                hits.c.traction,
                hits.c.flags,
            )
            .select_from(
                hits.outerjoin(
                    channel_snapshots,
                    (channel_snapshots.c.run_id == hits.c.run_id)
                    & (channel_snapshots.c.channel_id == hits.c.channel_id)
                    & (channel_snapshots.c.retain_until > now),
                )
            )
            .where(
                hits.c.hypothesis_id == hypothesis_id,
                hits.c.run_id == row["run_id"],
                hits.c.excluded_reason.is_(None),
                hits.c.retain_until > now,
            )
            .order_by(hits.c.income_high.desc().nulls_last(), hits.c.monthly_long_views.desc())
            .limit(MAX_CHANNELS)
        )
        channels = [
            {
                "channel_id": item["channel_id"],
                "title": item["title"],
                "subscribers": item["subscribers"],
                "monthly_long_views": item["monthly_long_views"],
                "income_low": _money(item["income_low"]),
                "income_high": _money(item["income_high"]),
                "traction": item["traction"],
                "flags": list(item["flags"]),
            }
            for item in connection.execute(query).mappings()
        ]
    return {
        "hypothesis": _hypothesis(row),
        "measurement": _measurement(row),
        "channels": channels,
        "channels_available": bool(channels),
        "research": _latest_research(connection).get(research_label(slug)),
    }
