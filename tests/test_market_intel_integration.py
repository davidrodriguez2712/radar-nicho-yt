# tests/test_market_intel_integration.py
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine

from nicheradar.config import Settings
from nicheradar.discovery.planning import request_counts_by_kind
from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.integrations.retention import expire
from nicheradar.market_intel.classify import save_classification, synthetic_classification
from nicheradar.market_intel.contracts import ListingCard
from nicheradar.market_intel.ingest import LISTING_RETENTION, upsert_cards
from nicheradar.market_intel.niches import save_decision
from nicheradar.market_intel.runs import get_schedule, set_paused
from nicheradar.market_intel.worker import tick_market
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.repositories.schema import (
    listing_classifications,
    listing_observations,
    market_niche_decisions,
    market_niche_snapshots,
    marketplace_listings,
)
from nicheradar.services.recovery import prepare_restore
from tests.test_market_api import AUTH, client
from tests.test_persistence import NOW

pytestmark = pytest.mark.postgres


def card(external_id: str) -> ListingCard:
    return ListingCard(
        external_id=external_id,
        url=f"https://dealbaron.test/listing/{external_id}",
        title="t",
        category="Games",
        income_monthly_usd=Decimal("300"),
    )


def count(db: Connection, table: sa.Table) -> int:
    return int(db.execute(sa.select(sa.func.count()).select_from(table)).scalar_one())


def test_expire_purges_old_listings_and_snapshots_but_keeps_owner_decisions(
    db: Connection,
) -> None:
    stale_seen = NOW - LISTING_RETENTION - timedelta(days=1)
    for external_id, seen in (("old", stale_seen), ("fresh", NOW)):
        upsert_cards(db, "dealbaron", [card(external_id)], seen, seen.date())
        listing_id = db.execute(
            sa.select(marketplace_listings.c.id).where(
                marketplace_listings.c.external_id == external_id
            )
        ).scalar_one()
        save_classification(
            db, listing_id, synthetic_classification("Games"), "synthetic_category_map", seen
        )
    for label, retain in (
        ("old_niche", NOW - timedelta(days=1)),
        ("new_niche", NOW + timedelta(days=9)),
    ):
        db.execute(
            sa.insert(market_niche_snapshots).values(
                id=uuid4(),
                snapshot_date=NOW.date(),
                niche_label=label,
                format="long",
                stats={},
                retain_until=retain,
            )
        )
    save_decision(db, "old_niche", "long", "tentativo", None, stale_seen)
    expire(db, NOW)
    remaining = db.execute(sa.select(marketplace_listings.c.external_id)).scalars().all()
    assert remaining == ["fresh"]
    assert count(db, listing_observations) == 1 and count(db, listing_classifications) == 1
    assert db.execute(sa.select(market_niche_snapshots.c.niche_label)).scalars().all() == [
        "new_niche"
    ]
    assert count(db, market_niche_decisions) == 1  # the owner's decisions never expire


def test_prepare_restore_pauses_the_market_scraper(db: Connection) -> None:
    set_paused(db, False, NOW)
    result = prepare_restore(db, NOW)
    assert get_schedule(db)["paused"] is True
    assert result["paused_market_schedules"] == 1


def test_a_market_run_is_not_the_radars_last_success(isolated_engine: Engine) -> None:
    api = client(isolated_engine)
    api.put("/api/v1/market/schedule", json={"paused": False}, headers=AUTH)
    outcome = tick_market(Settings(mode="synthetic"), isolated_engine, clock=lambda: NOW)
    assert outcome["status"] == "succeeded"
    status = api.get("/api/v1/status", headers=AUTH).json()
    assert status["last_success_at"] is None


def test_market_scrape_requests_do_not_shift_the_radar_exploration_balance(db: Connection) -> None:
    profile_id = seed_profile(db, CreatorProfile(), initial_catalog())
    runs = {
        "scheduled": {"discovery_kind": "catalog"},
        "market_scrape": {},
    }
    for trigger, configuration in runs.items():
        run_id = insert_record(
            db,
            "analysis_runs",
            {
                "profile_id": profile_id,
                "mode": "live",
                "trigger": trigger,
                "status": "succeeded",
                "configuration": configuration,
            },
        )
        insert_record(
            db,
            "provider_requests",
            {
                "run_id": run_id,
                "provider": "openai",
                "operation": "niche_match",
                "auth_scope": "test",
                "cache_key": trigger,
                "idempotency_key": trigger,
                "state": "sent",
                "sent_at": NOW,
            },
        )
    assert request_counts_by_kind(db, profile_id, "live") == [("catalog", 1)]
