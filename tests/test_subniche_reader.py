# tests/test_subniche_reader.py
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection

from nicheradar.config import Settings
from nicheradar.integrations.contracts import Cost, Operation
from nicheradar.repositories import schema_v1 as s
from nicheradar.services.budget import Limits, reserve
from nicheradar.services.requests import prepare_request
from nicheradar.subniche_discovery.reader import search_units_used_today, subniche_youtube_limits
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
