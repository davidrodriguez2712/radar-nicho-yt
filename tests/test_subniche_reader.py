# tests/test_subniche_reader.py
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection

from nicheradar.config import Settings
from nicheradar.integrations.contracts import Cost, Operation, ProviderError
from nicheradar.repositories import schema_v1 as s
from nicheradar.services.budget import Limits, reserve
from nicheradar.services.gateway import Gateway
from nicheradar.services.requests import prepare_request
from nicheradar.subniche_discovery.reader import (
    GatewayReader,
    search_units_used_today,
    subniche_youtube_limits,
)
from tests.subniche_samples import NOW, make_run


def test_subniche_limits_use_the_dedicated_settings() -> None:
    config = Settings(
        subniche_search_quota_per_run=500,
        subniche_search_quota_per_week=5000,
        subniche_search_quota_per_month=20000,
        subniche_detail_quota_per_run=7000,
    )
    limits = subniche_youtube_limits(config)
    assert limits["youtube_search_quota"] == Limits(
        operation=Decimal(100), run=Decimal(500), week=Decimal(5000), period=Decimal(20000)
    )
    assert limits["youtube_quota"].run == Decimal(7000)


def reserve_search(db: Connection, profile_id: UUID, run_id: UUID, when: datetime, n: int) -> None:
    request_id = prepare_request(
        db, run_id, "youtube", Operation.SEARCH, "scope", f"k{n}", f"idem-{n}", when
    )
    reserve(
        db,
        request_id,
        profile_id,
        (Cost(unit="youtube_search_quota", maximum=Decimal(100), source="test"),),
        {
            "youtube_search_quota": Limits(
                operation=Decimal(100),
                run=Decimal(10_000),
                week=Decimal(100_000),
                period=Decimal(1_000_000),
            )
        },
        when,
        "America/Lima",
    )
    # created_at is set by the database default (real now), not by `when`: pin it.
    db.execute(
        sa.update(s.cost_reservations)
        .where(s.cost_reservations.c.request_id == request_id)
        .values(created_at=when)
    )


@pytest.mark.postgres
def test_search_units_used_today_counts_only_the_local_day(db: Connection) -> None:
    _, analysis_id, profile_id = make_run(db)
    # 2026-10-31 12:00 UTC is 07:00 in Lima; Lima's day started at 05:00 UTC.
    reserve_search(db, profile_id, analysis_id, NOW, 1)
    reserve_search(db, profile_id, analysis_id, NOW - timedelta(hours=8), 2)  # 04:00 UTC: yesterday
    assert search_units_used_today(db, NOW, "America/Lima") == Decimal(100)


PACIFIC = "America/Los_Angeles"


@pytest.mark.postgres
def test_search_units_used_today_follows_the_pacific_quota_day(db: Connection) -> None:
    _, analysis_id, profile_id = make_run(db)
    # PDT is UTC-7: Pacific midnight of 2026-10-31 is 07:00 UTC.
    reserve_search(db, profile_id, analysis_id, datetime(2026, 10, 31, 6, 30, tzinfo=UTC), 1)
    reserve_search(db, profile_id, analysis_id, datetime(2026, 10, 31, 7, 10, tzinfo=UTC), 2)
    now = datetime(2026, 10, 31, 7, 30, tzinfo=UTC)
    assert search_units_used_today(db, now, PACIFIC) == Decimal(100)


@pytest.mark.postgres
def test_pacific_day_boundary_shifts_to_0800_utc_after_the_dst_change(db: Connection) -> None:
    _, analysis_id, profile_id = make_run(db)
    # PDT ended 2026-11-01 at 02:00 local: Nov 1 starts 07:00 UTC, Nov 2 starts 08:00 UTC.
    reserve_search(db, profile_id, analysis_id, datetime(2026, 11, 2, 7, 30, tzinfo=UTC), 1)
    reserve_search(db, profile_id, analysis_id, datetime(2026, 11, 2, 8, 10, tzinfo=UTC), 2)
    now = datetime(2026, 11, 2, 8, 30, tzinfo=UTC)
    assert search_units_used_today(db, now, PACIFIC) == Decimal(100)


class StubGateway:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, *_: Any) -> tuple[Any, None, None]:
        self.calls += 1
        batch = SimpleNamespace(videos=(), coverage=SimpleNamespace(next_page=None))
        return batch, None, None


def search_once(engine: Any, gateway: StubGateway, now: datetime) -> None:
    config = Settings(mode="live", subniche_search_units_per_day=100)
    reader = GatewayReader(cast(Gateway, gateway), engine, config, lambda: now)
    asyncio.run(reader.search("history", now - timedelta(days=30), None))


@pytest.mark.postgres
def test_reader_search_cap_resets_at_pacific_midnight(isolated_engine: Any) -> None:
    with isolated_engine.begin() as connection:
        _, analysis_id, profile_id = make_run(connection)
        reserve_search(
            connection, profile_id, analysis_id, datetime(2026, 10, 31, 6, 30, tzinfo=UTC), 1
        )
    gateway = StubGateway()
    # Lima midnight (05:00 UTC) already passed but Google's quota (07:00 UTC) has not reset.
    with pytest.raises(ProviderError, match="subniche_daily_search_cap"):
        search_once(isolated_engine, gateway, datetime(2026, 10, 31, 6, 45, tzinfo=UTC))
    assert gateway.calls == 0
    search_once(isolated_engine, gateway, datetime(2026, 10, 31, 7, 30, tzinfo=UTC))
    assert gateway.calls == 1
