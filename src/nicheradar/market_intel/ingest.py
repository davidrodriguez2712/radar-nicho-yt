# src/nicheradar/market_intel/ingest.py
"""Persistence of marketplace listings. Every figure is seller-declared and optional."""

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, NamedTuple
from uuid import UUID, uuid4

from sqlalchemy import Connection, case, select, update
from sqlalchemy.dialects.postgresql import insert

from nicheradar.market_intel.contracts import ListingCard, ListingDetail, channel_id_from_url
from nicheradar.repositories.schema import listing_observations as lo
from nicheradar.repositories.schema import marketplace_listings as ml

LISTING_RETENTION = timedelta(days=183)
MISSES_BEFORE_DISAPPEARED = 2


class UpsertResult(NamedTuple):
    seen: int
    new: int
    price_changed: int


def upsert_cards(
    connection: Connection,
    source: str,
    cards: Sequence[ListingCard],
    now: datetime,
    observed_on: date,
) -> UpsertResult:
    ids = [card.external_id for card in cards]
    existing: dict[str, tuple[UUID, Decimal | None]] = {}
    for start in range(0, len(ids), 500):
        rows = connection.execute(
            select(ml.c.external_id, ml.c.id, ml.c.price_usd).where(
                ml.c.source == source, ml.c.external_id.in_(ids[start : start + 500])
            )
        ).all()
        for found in rows:
            existing[found.external_id] = (found.id, found.price_usd)
    retain_until = now + LISTING_RETENTION
    new = changed = 0
    for card in cards:
        # A card that omits a figure must never erase one learned earlier from the detail page.
        known: dict[str, Any] = {
            key: value
            for key, value in {
                "category": card.category,
                "price_usd": card.price_usd,
                "subscribers": card.subscribers,
                "income_monthly_usd": card.income_monthly_usd,
            }.items()
            if value is not None
        }
        shared: dict[str, Any] = {
            "title": card.title,
            "status": "active",
            "last_seen_at": now,
            "consecutive_misses": 0,
            "retain_until": retain_until,
        } | known
        if card.external_id in existing:
            listing_id, previous_price = existing[card.external_id]
            if card.price_usd is not None and previous_price != card.price_usd:
                shared["detail_fetched_at"] = None
                changed += 1
            connection.execute(update(ml).where(ml.c.id == listing_id).values(**shared))
        else:
            listing_id = uuid4()
            new += 1
            connection.execute(
                insert(ml).values(
                    id=listing_id,
                    source=source,
                    external_id=card.external_id,
                    url=card.url,
                    first_seen_at=now,
                    **shared,
                )
            )
        observation = {
            "price_usd": card.price_usd,
            "subscribers": card.subscribers,
            "income_monthly_usd": card.income_monthly_usd,
        }
        connection.execute(
            insert(lo)
            .values(
                id=uuid4(),
                listing_id=listing_id,
                observed_on=observed_on,
                category=card.category,
                retain_until=retain_until,
                created_at=now,
                **observation,
            )
            .on_conflict_do_update(
                index_elements=["listing_id", "observed_on"],
                set_={**observation, "retain_until": retain_until},
            )
        )
    return UpsertResult(seen=len(cards), new=new, price_changed=changed)


def apply_detail(
    connection: Connection, source: str, detail: ListingDetail, now: datetime, observed_on: date
) -> bool:
    values: dict[str, Any] = {
        "title": detail.title,
        "channel_url": detail.channel_url,
        "youtube_channel_id": channel_id_from_url(detail.channel_url),
        "description": detail.description,
        "monetization": detail.monetization,
        "content_type": detail.content_type,
        "published_text": detail.published_text,
        "detail_fetched_at": now,
    }
    if detail.category is not None:
        values["category"] = detail.category
    if detail.price_usd is not None:
        values["price_usd"] = detail.price_usd
    if detail.subscribers is not None:
        values["subscribers"] = detail.subscribers
    # "$0 income" means the seller did not report income: it is not a declared income.
    if detail.income_monthly_usd is not None and detail.income_monthly_usd > 0:
        values["income_monthly_usd"] = detail.income_monthly_usd
    if detail.expense_monthly_usd is not None:
        values["expense_monthly_usd"] = detail.expense_monthly_usd
    listing_id = connection.execute(
        update(ml)
        .where(ml.c.source == source, ml.c.external_id == detail.external_id)
        .values(**values)
        .returning(ml.c.id)
    ).scalar_one_or_none()
    if listing_id is None:
        return False
    if detail.expense_monthly_usd is not None:
        connection.execute(
            update(lo)
            .where(lo.c.listing_id == listing_id, lo.c.observed_on == observed_on)
            .values(expense_monthly_usd=detail.expense_monthly_usd)
        )
    return True


def mark_detail_gone(connection: Connection, source: str, external_id: str, now: datetime) -> None:
    connection.execute(
        update(ml)
        .where(ml.c.source == source, ml.c.external_id == external_id)
        .values(status="disappeared", detail_fetched_at=now)
    )


def mark_detail_failed(
    connection: Connection, source: str, external_id: str, now: datetime
) -> None:
    connection.execute(
        update(ml)
        .where(ml.c.source == source, ml.c.external_id == external_id)
        .values(detail_fetched_at=now)
    )


def reconcile(connection: Connection, source: str, crawl_started_at: datetime) -> int:
    """Call ONLY after a complete, error-free crawl whose cards were upserted at that instant."""
    connection.execute(
        update(ml)
        .where(ml.c.source == source, ml.c.status == "active", ml.c.last_seen_at < crawl_started_at)
        .values(consecutive_misses=ml.c.consecutive_misses + 1)
    )
    result = connection.execute(
        update(ml)
        .where(
            ml.c.source == source,
            ml.c.status == "active",
            ml.c.consecutive_misses >= MISSES_BEFORE_DISAPPEARED,
        )
        .values(status="disappeared")
    )
    return int(result.rowcount)


def pending_detail(connection: Connection, source: str, limit: int) -> list[str]:
    declared_first = case((ml.c.income_monthly_usd > 0, 0), else_=1)
    rows = connection.execute(
        select(ml.c.external_id)
        .where(ml.c.source == source, ml.c.status == "active", ml.c.detail_fetched_at.is_(None))
        .order_by(declared_first, ml.c.first_seen_at.desc(), ml.c.external_id.desc())
        .limit(limit)
    ).scalars()
    return list(rows)
