# tests/test_market_intel_ingest.py
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection

from nicheradar.market_intel.contracts import ListingCard, ListingDetail
from nicheradar.market_intel.ingest import (
    LISTING_RETENTION,
    apply_detail,
    mark_detail_failed,
    mark_detail_gone,
    pending_detail,
    reconcile,
    upsert_cards,
)
from nicheradar.repositories.schema import listing_observations, marketplace_listings

NOW = datetime(2026, 10, 19, 12, tzinfo=UTC)
DAY = timedelta(days=1)
SOURCE = "dealbaron"


def card(
    external_id: str,
    *,
    price: str | None = "1000",
    subscribers: int | None = 10_000,
    income: str | None = None,
) -> ListingCard:
    return ListingCard(
        external_id=external_id,
        url=f"https://dealbaron.test/listing/{external_id}",
        title=f"Channel {external_id}",
        category="Games",
        price_usd=Decimal(price) if price is not None else None,
        subscribers=subscribers,
        income_monthly_usd=Decimal(income) if income is not None else None,
    )


def row(db: Connection, external_id: str) -> dict[str, object]:
    return dict(
        db.execute(
            sa.select(marketplace_listings).where(marketplace_listings.c.external_id == external_id)
        )
        .mappings()
        .one()
    )


def detail(external_id: str, **overrides: object) -> ListingDetail:
    values: dict[str, object] = {
        "external_id": external_id,
        "title": f"Channel {external_id}",
        "channel_url": "https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv",
        "price_usd": Decimal("1000"),
        "subscribers": 10_000,
        "income_monthly_usd": Decimal("0"),
        "expense_monthly_usd": Decimal("100"),
        "description": "faceless channel",
        "monetization": "yes",
        "content_type": "Unique content",
        "published_text": "2 days ago",
    }
    return ListingDetail.model_validate(values | overrides)


@pytest.mark.postgres
def test_upsert_creates_listings_and_daily_observations(db: Connection) -> None:
    result = upsert_cards(db, SOURCE, [card("1"), card("2", income="300")], NOW, NOW.date())
    assert (result.seen, result.new, result.price_changed) == (2, 2, 0)
    first = row(db, "1")
    assert first["status"] == "active" and first["consecutive_misses"] == 0
    assert first["retain_until"] == NOW + LISTING_RETENTION
    assert first["detail_fetched_at"] is None
    observations = db.execute(sa.select(listing_observations)).mappings().all()
    assert len(observations) == 2
    assert {o["origin"] for o in observations} == {"seller_declared"}


@pytest.mark.postgres
def test_upsert_is_idempotent_per_day_and_detects_price_change(db: Connection) -> None:
    upsert_cards(db, SOURCE, [card("1")], NOW, NOW.date())
    apply_detail(db, SOURCE, detail("1"), NOW, NOW.date())
    again = upsert_cards(db, SOURCE, [card("1")], NOW, NOW.date())
    assert (again.new, again.price_changed) == (0, 0)
    observations = sa.select(sa.func.count()).select_from(listing_observations)
    assert db.execute(observations).scalar_one() == 1
    assert row(db, "1")["detail_fetched_at"] == NOW
    changed = upsert_cards(db, SOURCE, [card("1", price="1500")], NOW + DAY, (NOW + DAY).date())
    assert changed.price_changed == 1
    assert row(db, "1")["detail_fetched_at"] is None
    assert row(db, "1")["price_usd"] == Decimal("1500")


@pytest.mark.postgres
def test_card_with_missing_values_does_not_erase_known_ones(db: Connection) -> None:
    upsert_cards(db, SOURCE, [card("1")], NOW, NOW.date())
    apply_detail(db, SOURCE, detail("1", income_monthly_usd=Decimal("500")), NOW, NOW.date())
    upsert_cards(
        db, SOURCE, [card("1", price=None, subscribers=None, income=None)], NOW + DAY, NOW.date()
    )
    stored = row(db, "1")
    assert stored["income_monthly_usd"] == Decimal("500")
    assert stored["price_usd"] == Decimal("1000") and stored["subscribers"] == 10_000


@pytest.mark.postgres
def test_apply_detail_sets_fields_and_zero_income_is_not_evidence(db: Connection) -> None:
    upsert_cards(db, SOURCE, [card("1", income="900")], NOW, NOW.date())
    assert apply_detail(db, SOURCE, detail("1"), NOW, NOW.date()) is True
    stored = row(db, "1")
    assert stored["income_monthly_usd"] == Decimal("900")  # detail "$0" did not overwrite it
    assert stored["expense_monthly_usd"] == Decimal("100")
    assert stored["youtube_channel_id"] == "UCabcdefghijklmnopqrstuv"
    assert stored["monetization"] == "yes" and stored["detail_fetched_at"] == NOW
    observation = db.execute(sa.select(listing_observations)).mappings().one()
    assert observation["expense_monthly_usd"] == Decimal("100")
    assert apply_detail(db, SOURCE, detail("missing"), NOW, NOW.date()) is False


@pytest.mark.postgres
def test_detail_gone_and_failed(db: Connection) -> None:
    upsert_cards(db, SOURCE, [card("1"), card("2")], NOW, NOW.date())
    mark_detail_gone(db, SOURCE, "1", NOW)
    mark_detail_failed(db, SOURCE, "2", NOW)
    assert row(db, "1")["status"] == "disappeared"
    assert row(db, "2")["status"] == "active" and row(db, "2")["detail_fetched_at"] == NOW


@pytest.mark.postgres
def test_reconcile_needs_two_complete_crawls_and_reappearance_resets(db: Connection) -> None:
    upsert_cards(db, SOURCE, [card("A"), card("B")], NOW, NOW.date())
    day2 = NOW + DAY
    upsert_cards(db, SOURCE, [card("A")], day2, day2.date())
    assert reconcile(db, SOURCE, day2) == 0
    assert row(db, "B")["status"] == "active" and row(db, "B")["consecutive_misses"] == 1
    day3 = NOW + 2 * DAY
    upsert_cards(db, SOURCE, [card("A")], day3, day3.date())
    assert reconcile(db, SOURCE, day3) == 1
    assert row(db, "B")["status"] == "disappeared" and row(db, "A")["status"] == "active"
    day4 = NOW + 3 * DAY
    upsert_cards(db, SOURCE, [card("A"), card("B")], day4, day4.date())
    assert row(db, "B")["status"] == "active" and row(db, "B")["consecutive_misses"] == 0


@pytest.mark.postgres
def test_pending_detail_prioritizes_declared_income_then_newest(db: Connection) -> None:
    upsert_cards(db, SOURCE, [card("old")], NOW - 5 * DAY, (NOW - 5 * DAY).date())
    upsert_cards(db, SOURCE, [card("income", income="400")], NOW - 4 * DAY, NOW.date())
    upsert_cards(db, SOURCE, [card("new")], NOW, NOW.date())
    apply_detail(db, SOURCE, detail("old"), NOW, NOW.date())
    assert pending_detail(db, SOURCE, 10) == ["income", "new"]
    assert pending_detail(db, SOURCE, 1) == ["income"]
    assert pending_detail(db, "other_source", 10) == []
