from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, select

from nicheradar.api import create_app
from nicheradar.config import Settings
from nicheradar.domain.production import EstimateRange
from nicheradar.integrations.synthetic import SyntheticProvider
from nicheradar.repositories import schema_v1 as s
from nicheradar.scoring.profit import SignedRange, estimate_profit
from tests.test_advertising_scoring import benchmark
from tests.test_discovery import run_pipeline
from tests.test_foundation import TOKEN
from tests.test_persistence import NOW
from tests.test_production_plans import complete_plan


@pytest.mark.parametrize(
    "missing_field",
    [
        "best_channel_views_per_day",
        "worst_channel_views_per_day",
        "videos_per_month",
        "advertising",
        "monthly_cost_usd",
    ],
)
def test_incomplete_without_any_real_input(missing_field: str) -> None:
    inputs: dict[str, object] = {
        "best_channel_views_per_day": 20.0,
        "worst_channel_views_per_day": 10.0,
        "videos_per_month": 4,
        "advertising": benchmark(),
        "monthly_cost_usd": EstimateRange(low=Decimal(10), high=Decimal(20)),
    }
    inputs[missing_field] = None
    result = estimate_profit(**inputs)  # type: ignore[arg-type]
    expected_missing = {
        "best_channel_views_per_day": "channel_view_rate",
        "worst_channel_views_per_day": "channel_view_rate",
        "videos_per_month": "videos_per_month",
        "advertising": "advertising_rate",
        "monthly_cost_usd": "production_cost",
    }
    assert result.status == "incomplete"
    assert expected_missing[missing_field] in result.missing
    assert result.monthly_profit_usd is None


def test_profit_range_can_cross_into_a_loss() -> None:
    result = estimate_profit(
        best_channel_views_per_day=20.0,
        worst_channel_views_per_day=10.0,
        videos_per_month=4,
        advertising=benchmark(),
        monthly_cost_usd=EstimateRange(low=Decimal(10), high=Decimal(20)),
    )
    assert result.status == "estimated"
    assert result.monthly_views == EstimateRange(low=Decimal(1200), high=Decimal(2400))
    assert result.monthly_revenue_usd == EstimateRange(low=Decimal("2.4"), high=Decimal("14.4"))
    assert result.monthly_profit_usd == SignedRange(low=Decimal("-17.6"), high=Decimal("4.4"))


@pytest.mark.postgres
def test_profit_endpoint_combines_real_cost_views_and_rpm(isolated_engine: Engine) -> None:
    provider = SyntheticProvider()
    run_pipeline(isolated_engine, NOW, provider)
    client = TestClient(
        create_app(
            Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine, clock=lambda: NOW
        )
    )
    with isolated_engine.connect() as connection:
        opportunity = connection.execute(
            select(s.opportunities.c.id).where(s.opportunities.c.format == "long")
        ).scalar_one()
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    path = f"/api/v1/opportunities/{opportunity}/profit"
    assert client.get(path).json()["status"] == "incomplete"

    plan_payload: dict[str, Any] = {
        "plan": complete_plan().model_dump(mode="json"),
        # The default recipe auto-applies during the worker's evaluation stage.
        "expected_version": 1,
    }
    assert (
        client.post(
            f"/api/v1/opportunities/{opportunity}/production", json=plan_payload
        ).status_code
        == 201
    )
    configuration = {
        "format": "long",
        "language": "en",
        "audience_key": "english-content-viewers",
        "advertising": benchmark().model_dump(mode="json"),
        "retention_basis": "fixture",
        "retain_until": (NOW + timedelta(days=10)).isoformat(),
    }
    assert (
        client.post(
            f"/api/v1/opportunities/{opportunity}/scoring",
            json={"configuration": configuration, "expected_version": 0},
        ).status_code
        == 201
    )
    result = client.get(path).json()
    assert result["status"] == "estimated"
    assert result["monthly_profit_usd"] is not None
