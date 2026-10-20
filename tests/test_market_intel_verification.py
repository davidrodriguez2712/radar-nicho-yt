# tests/test_market_intel_verification.py
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine

from nicheradar.config import Settings
from nicheradar.integrations.contracts import Channel, ProviderError
from nicheradar.market_intel.classify import save_classification, synthetic_classification
from nicheradar.market_intel.context import RunContext
from nicheradar.market_intel.contracts import ListingCard, ListingDetail
from nicheradar.market_intel.ingest import apply_detail, upsert_cards
from nicheradar.market_intel.sources.factory import build_source
from nicheradar.market_intel.verification import (
    VERIFICATION_TTL,
    pending_verification,
    save_verification,
    stage_verify,
    verification_status,
)
from nicheradar.repositories.schema import listing_verifications

NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)
SOURCE = "dealbaron"


@pytest.mark.parametrize(
    ("declared", "real", "expected"),
    [
        (100_000, 98_000, "verified"),
        (100_000, 130_000, "verified"),  # 23% apart: inside the 25% tolerance
        (100_000, 140_000, "mismatch"),
        (100_000, 50_000, "mismatch"),
        (None, 5_000, "verified"),
        (5_000, None, "unverifiable"),
        (0, 0, "verified"),
    ],
)
def test_verification_status(declared: int | None, real: int | None, expected: str) -> None:
    assert verification_status(declared, real) == expected


def seed(
    connection: Connection,
    external_id: str,
    *,
    income: int | None = 500,
    channel_url: str | None = "https://youtube.com/@someone",
    classified: bool = True,
    subscribers: int = 10_000,
) -> UUID:
    card = ListingCard(
        external_id=external_id,
        url=f"https://dealbaron.test/listing/{external_id}",
        title=f"Channel {external_id}",
        category="Games",
        subscribers=subscribers,
        income_monthly_usd=Decimal(income) if income is not None else None,
    )
    upsert_cards(connection, SOURCE, [card], NOW, NOW.date())
    detail = ListingDetail(external_id=external_id, title="t", channel_url=channel_url)
    apply_detail(connection, SOURCE, detail, NOW, NOW.date())
    listing_id: UUID = connection.execute(
        sa.text("SELECT id FROM marketplace_listings WHERE external_id = :e"),
        {"e": external_id},
    ).scalar_one()
    if classified:
        result = synthetic_classification("Games")
        save_classification(connection, listing_id, result, "synthetic_category_map", NOW)
    return listing_id


@pytest.mark.postgres
def test_pending_requires_income_url_classification_and_no_recent_check(db: Connection) -> None:
    best = seed(db, "best", income=900)
    seed(db, "second", income=400)
    seed(db, "no_income", income=None)
    seed(db, "no_url", channel_url=None)
    seed(db, "unclassified", classified=False)
    checked = seed(db, "checked", income=700)
    save_verification(db, checked, "UC1", 10_000, "verified", NOW - timedelta(days=5))
    pending = pending_verification(db, SOURCE, 10, NOW)
    assert [item["id"] for item in pending][0] == best
    assert len(pending) == 2 and pending[0]["channel_url"] == "https://youtube.com/@someone"
    assert len(pending_verification(db, SOURCE, 1, NOW)) == 1
    stale = NOW + VERIFICATION_TTL + timedelta(days=1)
    assert checked in [item["id"] for item in pending_verification(db, SOURCE, 10, stale)]


def context(engine: Engine, config: Settings, mode: str) -> RunContext:
    return RunContext(
        engine=engine,
        config=config,
        source=build_source(Settings(mode="synthetic")),
        run_id=uuid4(),
        analysis_run={"id": uuid4(), "profile_id": uuid4(), "mode": mode},
        owner="worker",
        started_at=NOW,
        clock=lambda: NOW,
    )


LIVE = Settings(
    mode="live",
    youtube_live_enabled=True,
    youtube_api_key=None,  # hermetic: never inherit the owner's .env key
    market_intel_verify_cap_per_run=10,
)


@pytest.mark.postgres
def test_stage_is_skipped_without_live_youtube(isolated_engine: Engine) -> None:
    synthetic = stage_verify(context(isolated_engine, LIVE, "synthetic"))
    assert synthetic == {"skipped": "synthetic_mode"}
    disabled = stage_verify(context(isolated_engine, Settings(mode="live"), "live"))
    assert disabled == {"skipped": "youtube_not_enabled"}
    no_cap = Settings(mode="live", youtube_live_enabled=True, market_intel_verify_cap_per_run=0)
    assert stage_verify(context(isolated_engine, no_cap, "live")) == {
        "skipped": "youtube_not_enabled"
    }


@pytest.mark.postgres
def test_stage_without_credentials_reports_a_partial_skip(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        seed(connection, "one")
    result = stage_verify(context(isolated_engine, LIVE, "live"))
    assert result == {"skipped": "authentication_required", "partial": True}


@pytest.mark.postgres
def test_stage_classifies_each_outcome_and_stops_on_a_quota_error(isolated_engine: Engine) -> None:
    incomes = {"ok": 600, "liar": 500, "gone": 400, "odd": 300, "limit": 200, "after": 100}
    with isolated_engine.begin() as connection:
        for name, income in incomes.items():
            seed(connection, name, income=income, channel_url=f"https://youtube.com/@{name}")

    async def resolver(channel_url: str) -> Channel:
        name = channel_url.rsplit("@", 1)[1]
        if name == "ok":
            return Channel(id="UCok", title="ok", subscribers=10_200)
        if name == "liar":
            return Channel(id="UCliar", title="liar", subscribers=2_000)
        if name == "gone":
            raise ProviderError("channel_not_found", not_sent=True)
        if name == "odd":
            raise ValueError("unsupported_channel_input")
        raise ProviderError("quota")

    result = stage_verify(context(isolated_engine, LIVE, "live"), resolver)
    assert result["checked"] == 4 and result["partial"] is True
    assert result["stopped_reason"] == "quota"
    assert (result["verified"], result["mismatch"], result["not_found"]) == (1, 1, 1)
    assert result["unverifiable"] == 1
    with isolated_engine.connect() as connection:
        rows = connection.execute(sa.select(listing_verifications)).mappings().all()
        assert {row["status"] for row in rows} == {
            "verified",
            "mismatch",
            "not_found",
            "unverifiable",
        }
        assert len(rows) == 4  # "limit" stopped the batch and "after" was never checked
        verified = next(row for row in rows if row["status"] == "verified")
        assert verified["real_subscribers"] == 10_200 and verified["youtube_channel_id"] == "UCok"

    async def healthy(channel_url: str) -> Channel:
        return Channel(id="UCfine", title="fine", subscribers=10_000)

    again = stage_verify(context(isolated_engine, LIVE, "live"), healthy)
    assert again["checked"] == 2  # only "limit" and "after": the four checks are not repeated
