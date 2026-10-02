from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, insert

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.integrations.contracts import Cost, ProviderError
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.repositories.schema import credit_balances
from nicheradar.services.budget import Limits, reserve
from tests.test_persistence import NOW


def test_new_budget_fields_have_conservative_defaults() -> None:
    settings = Settings()
    assert settings.youtube_search_quota_per_run == 100
    assert settings.youtube_search_quota_per_week == 100
    assert settings.youtube_search_quota_per_month == 300
    assert settings.youtube_detail_quota_per_run == 100
    assert settings.youtube_detail_quota_per_week == 500
    assert settings.youtube_detail_quota_per_month == 2000
    profile = CreatorProfile()
    assert profile.channel_analysis_credits_per_run == 50


def _prepared_request(db: Connection, profile_id: UUID, trigger: str) -> UUID:
    run_id = insert_record(
        db,
        "analysis_runs",
        {
            "profile_id": profile_id,
            "mode": "live",
            "trigger": trigger,
            "status": "running",
            "configuration": {},
        },
    )
    request_id = insert_record(
        db,
        "provider_requests",
        {
            "run_id": run_id,
            "provider": "vidiq",
            "operation": "channel_search",
            "auth_scope": "test",
            "cache_key": uuid4().hex + uuid4().hex,
            "idempotency_key": str(uuid4()),
            "state": "prepared",
        },
    )
    return request_id


@pytest.mark.postgres
def test_channel_analysis_trigger_uses_its_own_run_cap(db: Connection) -> None:
    profile = CreatorProfile(
        credits_per_run=5,
        channel_analysis_credits_per_run=50,
        credits_per_week=200,
        credits_per_cycle=400,
    )
    profile_id = seed_profile(db, profile, initial_catalog())
    db.execute(
        insert(credit_balances).values(
            provider="vidiq",
            auth_scope="test",
            unit="vidiq_credit",
            renewable_remaining=Decimal(1000),
            renewable_allocation=Decimal(1000),
            additional_remaining=Decimal(0),
            cycle_started_at=NOW,
            renews_at=NOW + timedelta(days=30),
            observed_at=NOW,
            retain_until=NOW + timedelta(days=7),
            refresh_required=False,
            confirmed_usage=Decimal(0),
        )
    )
    limits = {
        "vidiq_credit": Limits(
            operation=Decimal(50), run=Decimal(50), week=Decimal(200), period=Decimal(400)
        )
    }
    costs = (Cost(unit="vidiq_credit", maximum=Decimal(30), source="test"),)

    manual_request = _prepared_request(db, profile_id, "manual")
    with pytest.raises(ProviderError):  # "run_budget_exhausted": 30 > credits_per_run=5
        reserve(db, manual_request, profile_id, costs, limits, NOW)

    analysis_request = _prepared_request(db, profile_id, "channel_analysis")
    reserve(db, analysis_request, profile_id, costs, limits, NOW)  # 30 <= 50: must not raise
