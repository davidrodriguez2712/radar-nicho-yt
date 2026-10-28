# tests/test_market_intel_schema.py
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, inspect
from sqlalchemy.exc import IntegrityError

from nicheradar.config import Settings
from nicheradar.repositories import schema

NOW = datetime(2026, 10, 19, 12, tzinfo=UTC)
NEW_TABLES = (
    "market_intel_schedule",
    "market_scrape_runs",
    "marketplace_listings",
    "listing_observations",
    "listing_classifications",
    "listing_verifications",
    "listing_evidence",
    "niche_automation_priors",
    "market_niche_snapshots",
    "market_niche_decisions",
)


def listing(db: Connection, external_id: str = "570976") -> UUID:
    table = schema.marketplace_listings
    listing_id = uuid4()
    db.execute(
        sa.insert(table).values(
            id=listing_id,
            source="dealbaron",
            external_id=external_id,
            url=f"https://dealbaron.com/listing/{external_id}",
            title="Calm Money Stories",
            first_seen_at=NOW,
            last_seen_at=NOW,
            retain_until=NOW + timedelta(days=183),
        )
    )
    return listing_id


def test_settings_defaults_and_bounds() -> None:
    config = Settings()
    assert config.market_intel_request_delay_seconds == 1.0
    assert config.market_intel_max_pages == 200
    assert config.market_intel_detail_cap_per_run == 300
    assert config.market_intel_classify_cap_per_run == 100
    assert config.market_intel_verify_cap_per_run == 20
    assert config.market_intel_live_enabled is False
    with pytest.raises(ValueError):
        Settings(market_intel_request_delay_seconds=0)


@pytest.mark.postgres
def test_tables_exist_and_match_metadata(db: Connection) -> None:
    inspector = inspect(db)
    existing = set(inspector.get_table_names())
    for name in NEW_TABLES:
        assert name in existing
        columns = {column["name"] for column in inspector.get_columns(name)}
        assert columns == set(schema.metadata.tables[name].c.keys())


@pytest.mark.postgres
def test_listing_defaults_and_uniqueness(db: Connection) -> None:
    listing(db)
    row = db.execute(sa.select(schema.marketplace_listings)).mappings().one()
    assert row["status"] == "active" and row["consecutive_misses"] == 0
    with pytest.raises(IntegrityError), db.begin_nested():
        listing(db)


@pytest.mark.postgres
def test_observation_unique_per_day_and_cascade_delete(db: Connection) -> None:
    listing_id = listing(db)
    values: dict[str, Any] = {
        "listing_id": listing_id,
        "observed_on": NOW.date(),
        "retain_until": NOW + timedelta(days=183),
        "created_at": NOW,
    }
    db.execute(sa.insert(schema.listing_observations).values(id=uuid4(), **values))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(sa.insert(schema.listing_observations).values(id=uuid4(), **values))
    db.execute(sa.delete(schema.marketplace_listings))
    remaining = sa.select(sa.func.count()).select_from(schema.listing_observations)
    assert db.execute(remaining).scalar_one() == 0


@pytest.mark.postgres
def test_schedule_is_born_paused_and_status_checks(db: Connection) -> None:
    db.execute(
        sa.insert(schema.market_intel_schedule).values(
            id=uuid4(),
            schedule_key="market_intel_scrape",
            interval_seconds=86400,
            next_due_at=NOW,
            configuration={},
        )
    )
    paused = db.execute(sa.select(schema.market_intel_schedule.c.paused)).scalar_one()
    assert paused is True
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            sa.insert(schema.market_scrape_runs).values(
                id=uuid4(), run_key="x", status="bogus", stage="list", created_at=NOW
            )
        )


@pytest.mark.postgres
def test_backup_guard_accepts_market_data_but_rejects_unpaused_schedule(db: Connection) -> None:
    from scripts.backup_snapshot import inspect_snapshot

    db.execute(
        sa.insert(schema.market_intel_schedule).values(
            id=uuid4(),
            schedule_key="market_intel_scrape",
            interval_seconds=86400,
            next_due_at=NOW,
            configuration={},
            paused=False,
        )
    )
    with pytest.raises(ValueError, match="market_intel_not_paused"):
        inspect_snapshot(db)
    db.execute(sa.update(schema.market_intel_schedule).values(paused=True))
    listing(db)
    assert inspect_snapshot(db)["scope"] == "bootstrap+research"
