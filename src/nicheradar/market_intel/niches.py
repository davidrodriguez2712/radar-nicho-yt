# src/nicheradar/market_intel/niches.py
"""Backlog aggregation: scores are computed on the fly from listings, never stored."""

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert

from nicheradar.market_intel.classify import PROMPT_VERSION
from nicheradar.market_intel.ingest import LISTING_RETENTION
from nicheradar.market_intel.scoring import (
    ListingFacts,
    automation_score,
    confidence,
    niche_metrics,
    opportunity_score,
)
from nicheradar.repositories.schema import (
    advertising_benchmarks,
    listing_classifications,
    listing_verifications,
    market_niche_decisions,
    market_niche_snapshots,
    marketplace_listings,
    niche_automation_priors,
)

ml, lc, lv = marketplace_listings, listing_classifications, listing_verifications
WINDOW_DAYS = 90
TREND_DAYS = 30
Key = tuple[str, str]


def niche_key(niche_label: str | None, other_label: str | None) -> str:
    return niche_label if niche_label else f"other:{other_label}"


def _format(value: str) -> str:
    # "unknown" is treated as long-form: only an explicit Shorts category is separated.
    return "shorts" if value == "shorts" else "long"


def _latest_verification() -> Any:
    return (
        select(lv.c.listing_id, lv.c.status, lv.c.real_subscribers)
        .distinct(lv.c.listing_id)
        .order_by(lv.c.listing_id, lv.c.checked_at.desc())
        .subquery()
    )


def _group_rows(connection: Connection, now: datetime) -> dict[Key, list[ListingFacts]]:
    verification = _latest_verification()
    rows = connection.execute(
        select(
            ml.c.status,
            ml.c.price_usd,
            ml.c.subscribers,
            ml.c.income_monthly_usd,
            ml.c.expense_monthly_usd,
            ml.c.last_seen_at,
            lc.c.niche_label,
            lc.c.other_label,
            lc.c.format,
            lc.c.traits,
            verification.c.status.label("verification"),
        )
        .select_from(
            ml.join(
                lc, and_(lc.c.listing_id == ml.c.id, lc.c.prompt_version == PROMPT_VERSION)
            ).outerjoin(verification, verification.c.listing_id == ml.c.id)
        )
        .where(
            ml.c.last_seen_at >= now - timedelta(days=WINDOW_DAYS),
            or_(lc.c.niche_label.is_not(None), lc.c.other_label.is_not(None)),
        )
    ).all()
    groups: dict[Key, list[ListingFacts]] = {}
    for row in rows:
        key = (niche_key(row.niche_label, row.other_label), _format(row.format))
        groups.setdefault(key, []).append(
            ListingFacts(
                status=row.status,
                price_usd=float(row.price_usd) if row.price_usd is not None else None,
                subscribers=row.subscribers,
                income_usd=float(row.income_monthly_usd)
                if row.income_monthly_usd is not None
                else None,
                expense_usd=float(row.expense_monthly_usd)
                if row.expense_monthly_usd is not None
                else None,
                verification=row.verification,
                days_since_seen=(now - row.last_seen_at).days,
                traits=dict(row.traits),
            )
        )
    return groups


def _rpm_midpoints(connection: Connection) -> dict[str, float]:
    rows = connection.execute(
        select(
            advertising_benchmarks.c.niche_label,
            advertising_benchmarks.c.rate_low,
            advertising_benchmarks.c.rate_high,
        ).where(advertising_benchmarks.c.format == "long")
    ).all()
    return {row.niche_label: float(row.rate_low + row.rate_high) / 2 for row in rows}


def _priors(connection: Connection) -> dict[str, dict[str, int | None]]:
    rows = connection.execute(
        select(niche_automation_priors.c.niche_label, niche_automation_priors.c.traits)
    ).all()
    return {row.niche_label: dict(row.traits) for row in rows}


def latest_decisions(connection: Connection) -> dict[Key, dict[str, Any]]:
    d = market_niche_decisions
    rows = connection.execute(
        select(d.c.niche_label, d.c.format, d.c.decision, d.c.note, d.c.created_at)
        .distinct(d.c.niche_label, d.c.format)
        .order_by(d.c.niche_label, d.c.format, d.c.created_at.desc())
    ).all()
    return {
        (row.niche_label, row.format): {
            "decision": row.decision,
            "note": row.note,
            "decided_at": row.created_at,
        }
        for row in rows
    }


def save_decision(
    connection: Connection,
    label: str,
    format: str,
    decision: str,
    note: str | None,
    now: datetime,
) -> None:
    d = market_niche_decisions
    latest = connection.execute(
        select(func.max(d.c.created_at)).where(d.c.niche_label == label, d.c.format == format)
    ).scalar_one()
    # "Latest decision wins" must be deterministic even when two arrive in the same instant.
    created_at = now if latest is None or now > latest else latest + timedelta(microseconds=1)
    connection.execute(
        insert(d).values(
            id=uuid4(),
            niche_label=label,
            format=format,
            decision=decision,
            note=note,
            created_at=created_at,
        )
    )


def _trend_deltas(
    connection: Connection, now: datetime, current: dict[Key, float | None], timezone: str
) -> dict[Key, float | None]:
    today = now.astimezone(ZoneInfo(timezone)).date()
    s = market_niche_snapshots
    rows = connection.execute(
        select(s.c.niche_label, s.c.format, s.c.stats)
        .distinct(s.c.niche_label, s.c.format)
        .where(
            s.c.snapshot_date >= today - timedelta(days=TREND_DAYS),
            s.c.snapshot_date < today,
        )
        .order_by(s.c.niche_label, s.c.format, s.c.snapshot_date)
    ).all()
    earliest = {(row.niche_label, row.format): row.stats.get("opportunity") for row in rows}
    deltas: dict[Key, float | None] = {}
    for key, value in current.items():
        before = earliest.get(key)
        deltas[key] = None if value is None or before is None else round(value - before, 1)
    return deltas


def scored_niches(
    connection: Connection, now: datetime, timezone: str = "UTC"
) -> list[dict[str, Any]]:
    groups = _group_rows(connection, now)
    midpoints, priors = _rpm_midpoints(connection), _priors(connection)
    decisions = latest_decisions(connection)
    items: list[dict[str, Any]] = []
    for (label, fmt), facts in groups.items():
        metrics = niche_metrics(facts)
        rpm = midpoints.get(label) if fmt == "long" else None
        items.append(
            {
                "niche_label": label,
                "format": fmt,
                "opportunity": opportunity_score(metrics, rpm),
                "automation": automation_score([fact.traits for fact in facts], priors.get(label)),
                "confidence": confidence(metrics),
                "metrics": metrics,
                "rpm_mid": rpm,
                "rpm_state": "calibrated" if rpm is not None else "uncalibrated",
                "decision": decisions.get((label, fmt))
                or {"decision": "nuevo", "note": None, "decided_at": None},
            }
        )
    deltas = _trend_deltas(
        connection,
        now,
        {(i["niche_label"], i["format"]): i["opportunity"]["value"] for i in items},
        timezone,
    )
    for item in items:
        item["trend"] = deltas[(item["niche_label"], item["format"])]
    return items


def backlog(
    connection: Connection,
    now: datetime,
    *,
    format: str | None = None,
    order: str = "opportunity",
    include_discarded: bool = False,
    limit: int = 50,
    offset: int = 0,
    timezone: str = "UTC",
) -> dict[str, Any]:
    items = scored_niches(connection, now, timezone)
    if format is not None:
        items = [item for item in items if item["format"] == format]
    if not include_discarded:
        items = [item for item in items if item["decision"]["decision"] != "descartado"]
    field = "automation" if order == "automation" else "opportunity"
    # Niches without a score (insufficient evidence) always sort after scored ones.
    items.sort(
        key=lambda item: (
            item[field]["value"] is None,
            -(item[field]["value"] or 0.0),
            item["niche_label"],
        )
    )
    return {
        "items": items[offset : offset + limit],
        "total": len(items),
        "limit": limit,
        "offset": offset,
    }


def language_mix(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Share of listings per language, largest first; ``unknown`` lacks a detected language."""
    counts: dict[str, int] = {}
    for item in listings:
        language = item["language"]
        counts[language] = counts.get(language, 0) + 1
    ordered = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0] == "unknown", pair[0]))
    return [
        {"language": language, "share_pct": round(100 * count / len(listings), 1)}
        for language, count in ordered
    ]


def niche_detail(
    connection: Connection, label: str, format: str, now: datetime, timezone: str = "UTC"
) -> dict[str, Any] | None:
    niche = next(
        (
            item
            for item in scored_niches(connection, now, timezone)
            if item["niche_label"] == label and item["format"] == format
        ),
        None,
    )
    if niche is None:
        return None
    verification = _latest_verification()
    match = (
        and_(lc.c.niche_label.is_(None), lc.c.other_label == label.removeprefix("other:"))
        if label.startswith("other:")
        else lc.c.niche_label == label
    )
    shorts = lc.c.format == "shorts" if format == "shorts" else lc.c.format != "shorts"
    rows = connection.execute(
        select(
            ml.c.title,
            ml.c.url,
            ml.c.channel_url,
            ml.c.status,
            ml.c.category,
            lc.c.language,
            ml.c.price_usd,
            ml.c.subscribers,
            ml.c.income_monthly_usd,
            ml.c.expense_monthly_usd,
            ml.c.first_seen_at,
            ml.c.last_seen_at,
            verification.c.status.label("verification"),
            verification.c.real_subscribers,
        )
        .select_from(
            ml.join(
                lc, and_(lc.c.listing_id == ml.c.id, lc.c.prompt_version == PROMPT_VERSION)
            ).outerjoin(verification, verification.c.listing_id == ml.c.id)
        )
        .where(match, shorts, ml.c.last_seen_at >= now - timedelta(days=WINDOW_DAYS))
        .order_by(ml.c.income_monthly_usd.desc().nulls_last(), ml.c.first_seen_at.desc())
    ).mappings()

    def number(value: Any) -> float | None:
        return float(value) if value is not None else None

    s = market_niche_snapshots
    history = connection.execute(
        select(s.c.snapshot_date, s.c.stats)
        .where(s.c.niche_label == label, s.c.format == format)
        .order_by(s.c.snapshot_date)
    ).all()
    listings = [
        {
            "title": row["title"],
            "url": row["url"],
            "channel_url": row["channel_url"],
            "status": row["status"],
            "category": row["category"],
            "language": row["language"],
            "price_usd": number(row["price_usd"]),
            "subscribers": row["subscribers"],
            "income_monthly_usd": number(row["income_monthly_usd"]),
            "expense_monthly_usd": number(row["expense_monthly_usd"]),
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "verification": row["verification"],
            "real_subscribers": row["real_subscribers"],
            "seller_declared": True,
        }
        for row in rows
    ]
    return {
        "niche": niche,
        "listings": listings,
        "language_mix": language_mix(listings),
        "history": [{"date": row.snapshot_date, **row.stats} for row in history],
    }


def build_snapshots(connection: Connection, now: datetime, timezone: str = "UTC") -> int:
    # The snapshot day is the LOCAL day, like run_key and observed_on, so a late-evening run
    # never lands on tomorrow's row and overwrites it.
    snapshot_date = now.astimezone(ZoneInfo(timezone)).date()
    items = scored_niches(connection, now, timezone)
    for item in items:
        stats = {
            "opportunity": item["opportunity"]["value"],
            "state": item["opportunity"]["state"],
            "automation": item["automation"]["value"],
            "n_listings": item["metrics"]["n_listings"],
            "income_median": item["metrics"]["income_median"],
        }
        values = {"stats": stats, "retain_until": now + LISTING_RETENTION}
        connection.execute(
            insert(market_niche_snapshots)
            .values(
                id=uuid4(),
                snapshot_date=snapshot_date,
                niche_label=item["niche_label"],
                format=item["format"],
                **values,
            )
            .on_conflict_do_update(
                index_elements=["snapshot_date", "niche_label", "format"], set_=values
            )
        )
    return len(items)
