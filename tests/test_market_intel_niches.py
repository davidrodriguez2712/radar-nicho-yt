# tests/test_market_intel_niches.py
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError

from nicheradar.market_intel.classify import (
    TRAIT_KEYS,
    ListingClassification,
    save_classification,
)
from nicheradar.market_intel.contracts import ListingCard, ListingDetail
from nicheradar.market_intel.ingest import LISTING_RETENTION, apply_detail, upsert_cards
from nicheradar.market_intel.niches import (
    backlog,
    build_snapshots,
    niche_detail,
    niche_key,
    save_decision,
    scored_niches,
)
from nicheradar.repositories.schema import (
    listing_verifications,
    market_niche_snapshots,
    niche_automation_priors,
)
from tests.test_persistence import NOW

SOURCE = "dealbaron"
counter = iter(range(1, 10_000))


def seed(
    db: Connection,
    niche: str | None,
    income: float | None,
    *,
    fmt: str = "long",
    language: str = "en",
    other: str | None = None,
    subscribers: int = 20_000,
    price: float = 30_000,
    expense: float = 100,
    traits: dict[str, int | None] | None = None,
) -> UUID:
    external_id = str(next(counter))
    upsert_cards(
        db,
        SOURCE,
        [
            ListingCard(
                external_id=external_id,
                url=f"https://dealbaron.test/listing/{external_id}",
                title=f"Channel {external_id}",
                category="Games",
                price_usd=Decimal(str(price)),
                subscribers=subscribers,
                income_monthly_usd=None if income is None else Decimal(str(income)),
            )
        ],
        NOW,
        NOW.date(),
    )
    apply_detail(
        db,
        SOURCE,
        ListingDetail(
            external_id=external_id,
            title=f"Channel {external_id}",
            channel_url=f"https://www.youtube.com/@channel{external_id}",
            expense_monthly_usd=Decimal(str(expense)),
        ),
        NOW,
        NOW.date(),
    )
    listing_id: UUID = db.execute(
        sa.text("SELECT id FROM marketplace_listings WHERE external_id = :e"), {"e": external_id}
    ).scalar_one()
    save_classification(
        db,
        listing_id,
        ListingClassification(
            niche_label=niche,
            other_label=other,
            format="shorts" if fmt == "shorts" else "long",
            language=language,
            traits=traits or dict.fromkeys(TRAIT_KEYS, 2),
            actual_usd=None,
            reason="response_received",
        ),
        "llm",
        NOW,
    )
    return listing_id


def seed_niche(
    db: Connection, niche: str | None, incomes: tuple[float, ...], **kwargs: Any
) -> None:
    for income in incomes:
        seed(db, niche, income, **kwargs)


def keyed(items: list[dict[str, object]]) -> dict[tuple[object, object], dict[str, object]]:
    return {(item["niche_label"], item["format"]): item for item in items}


def test_niche_key_marks_free_labels() -> None:
    assert niche_key("personal_finance", None) == "personal_finance"
    assert niche_key(None, "asmr_sleep") == "other:asmr_sleep"


@pytest.mark.postgres
def test_backlog_orders_by_opportunity_with_insufficient_niches_last(db: Connection) -> None:
    seed_niche(db, "personal_finance", (1500, 2000, 2500, 3000), price=67_500)
    seed_niche(db, "gaming_general", (60, 80, 100, 120), price=720, expense=90)
    seed_niche(db, "cooking_recipes", (400, 500))
    items = backlog(db, NOW)["items"]
    assert [item["niche_label"] for item in items] == [
        "personal_finance",
        "gaming_general",
        "cooking_recipes",
    ]
    assert items[0]["opportunity"]["value"] > items[1]["opportunity"]["value"]
    assert items[2]["opportunity"]["state"] == "insufficient_evidence"
    assert items[0]["decision"]["decision"] == "nuevo"
    assert items[0]["rpm_state"] == "calibrated" and items[0]["rpm_mid"] == 10.0


@pytest.mark.postgres
def test_long_and_shorts_are_scored_apart_and_shorts_rpm_is_uncalibrated(db: Connection) -> None:
    seed_niche(db, "personal_finance", (900, 1000, 1100, 1200))
    seed_niche(db, "personal_finance", (900, 1000, 1100, 1200), fmt="shorts")
    items = keyed(scored_niches(db, NOW))
    assert items[("personal_finance", "long")]["rpm_state"] == "calibrated"
    assert items[("personal_finance", "shorts")]["rpm_state"] == "uncalibrated"
    assert items[("personal_finance", "shorts")]["rpm_mid"] is None
    assert [i["format"] for i in backlog(db, NOW, format="shorts")["items"]] == ["shorts"]


@pytest.mark.postgres
def test_free_labels_group_apart_and_unusable_classifications_are_hidden(db: Connection) -> None:
    seed_niche(db, None, (300, 400, 500), other="asmr_sleep_sounds")
    seed(db, None, 900)  # unusable: no niche and no free label
    items = keyed(scored_niches(db, NOW))
    assert set(items) == {("other:asmr_sleep_sounds", "long")}
    assert items[("other:asmr_sleep_sounds", "long")]["rpm_state"] == "uncalibrated"


@pytest.mark.postgres
def test_zero_income_does_not_count_and_verification_filters_declared_figures(
    db: Connection,
) -> None:
    ids = [seed(db, "personal_finance", income) for income in (0, 300, 400, 500, 600)]
    db.execute(
        sa.insert(listing_verifications).values(
            id=uuid4(),
            listing_id=ids[4],
            youtube_channel_id="UCx",
            real_subscribers=10,
            status="mismatch",
            checked_at=NOW,
            retain_until=NOW + LISTING_RETENTION,
        )
    )
    metrics = scored_niches(db, NOW)[0]["metrics"]
    assert metrics["n_listings"] == 5 and metrics["n_income"] == 3
    assert metrics["income_median"] == 400


@pytest.mark.postgres
def test_automation_uses_listing_traits_then_the_niche_prior(db: Connection) -> None:
    blank: dict[str, int | None] = dict.fromkeys(TRAIT_KEYS)
    seed_niche(db, "personal_finance", (500, 600, 700), traits=blank)
    db.execute(
        sa.insert(niche_automation_priors).values(
            id=uuid4(),
            niche_label="personal_finance",
            traits=dict.fromkeys(TRAIT_KEYS, 2),
            prompt_version="prior-v1",
            created_at=NOW,
        )
    )
    item = backlog(db, NOW, order="automation")["items"][0]
    assert item["automation"]["value"] == 100
    assert item["automation"]["policy_risk"]["level"] == "alto"


@pytest.mark.postgres
def test_decisions_hide_discarded_and_latest_wins(db: Connection) -> None:
    seed_niche(db, "personal_finance", (500, 600, 700))
    save_decision(db, "personal_finance", "long", "tentativo", "mirar", NOW)
    assert backlog(db, NOW)["items"][0]["decision"]["decision"] == "tentativo"
    save_decision(db, "personal_finance", "long", "descartado", None, NOW)  # same instant
    assert backlog(db, NOW)["items"] == []
    assert len(backlog(db, NOW, include_discarded=True)["items"]) == 1
    with pytest.raises(IntegrityError), db.begin_nested():
        save_decision(db, "personal_finance", "long", "bogus", None, NOW)


@pytest.mark.postgres
def test_snapshots_are_idempotent_and_drive_the_trend(db: Connection) -> None:
    seed_niche(db, "personal_finance", (1500, 2000, 2500, 3000))
    assert build_snapshots(db, NOW) == 1
    assert build_snapshots(db, NOW) == 1
    assert (
        db.execute(sa.select(sa.func.count()).select_from(market_niche_snapshots)).scalar_one() == 1
    )
    old = NOW - timedelta(days=20)
    db.execute(
        sa.insert(market_niche_snapshots).values(
            id=uuid4(),
            snapshot_date=old.date(),
            niche_label="personal_finance",
            format="long",
            stats={"opportunity": 10.0},
            retain_until=old + LISTING_RETENTION,
        )
    )
    item = backlog(db, NOW)["items"][0]
    assert item["trend"] == pytest.approx(item["opportunity"]["value"] - 10.0)


@pytest.mark.postgres
def test_snapshot_date_follows_the_local_day(db: Connection) -> None:
    seed_niche(db, "personal_finance", (1500, 2000, 2500, 3000))
    late_evening_in_lima = datetime(2026, 10, 20, 3, 0, tzinfo=UTC)  # still Oct 19 there
    build_snapshots(db, late_evening_in_lima, "America/Lima")
    dates = db.execute(sa.select(market_niche_snapshots.c.snapshot_date)).scalars().all()
    assert dates == [date(2026, 10, 19)]


@pytest.mark.postgres
def test_niche_detail_lists_listings_and_history(db: Connection) -> None:
    seed_niche(db, "personal_finance", (500, 600, 700))
    detail = niche_detail(db, "personal_finance", "long", NOW)
    assert detail is not None and len(detail["listings"]) == 3
    assert detail["listings"][0]["seller_declared"] is True
    assert detail["niche"]["niche_label"] == "personal_finance"
    assert niche_detail(db, "nope", "long", NOW) is None
