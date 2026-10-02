from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import Engine, select

from nicheradar.api import create_app
from nicheradar.config import Settings
from nicheradar.discovery.sampling import sample
from nicheradar.domain.profile import CreatorProfile, VideoFormat
from nicheradar.features.metrics import CohortMetrics, calculate
from nicheradar.integrations.retention import expire
from nicheradar.integrations.synthetic import SyntheticProvider
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.schema import opportunity_scoring_configs
from nicheradar.scoring.advertising import AdvertisingBenchmark, assess_advertising
from nicheradar.scoring.combined import combine, final_score
from nicheradar.scoring.market import MarketEvaluation, References, evaluate_market, normalize
from nicheradar.services.production import evaluate_plan
from nicheradar.services.scoring import ScoringConfiguration
from tests.test_discovery import run_pipeline
from tests.test_evaluation import fixture_videos
from tests.test_foundation import TOKEN
from tests.test_persistence import NOW
from tests.test_production_plans import complete_plan


def benchmark(**changes: Any) -> AdvertisingBenchmark:
    return AdvertisingBenchmark.model_validate(
        {
            "version": "invented-ad-fixture-v1",
            "source": "invented test, not a real RPM",
            "origin": "synthetic",
            "format": "long",
            "language": "en",
            "audience_key": "english-content-viewers",
            "audience_geography": "fixture-region",
            "geography_basis": "assumed",
            "geography_evidence": "explicit synthetic audience assumption",
            "unit": "usd_ads_per_1000_views",
            "rate": {"low": "2", "high": "6"},
            "revenue_scope": "youtube_ads_only_after_revenue_share",
            "assumptions": "Invented post-activation range; not observed competitor income",
            "observed_at": NOW,
            "valid_until": NOW + timedelta(days=20),
            "usage": "enabled",
            "usage_evidence": "original synthetic fixture",
        }
        | changes
    )


def references(**changes: Any) -> References:
    return References.model_validate(
        {
            "version": "invented-reference-v1",
            "format": "long",
            "source": "synthetic fixture",
            "synthetic": True,
            "reviewed": True,
            "demand_p90_by_age": {"8-30": 100},
            "monetization_p90": 10,
            "monetization_unit": "usd_ads_per_1000_views",
            "monetization_geography": "fixture-region",
            "trend_p90_abs_change": 1,
        }
        | changes
    )


def metrics() -> CohortMetrics:
    return calculate(
        sample(
            fixture_videos(),
            now=NOW,
            format=VideoFormat.LONG,
            language="en",
            terms=("science",),
            selection_method="recent",
        ),
        NOW,
    )


def market_for(ad: AdvertisingBenchmark | None, **changes: Any) -> MarketEvaluation:
    assessment = assess_advertising(
        ad,
        format=VideoFormat.LONG,
        language="en",
        audience_key="english-content-viewers",
        synthetic=True,
        now=NOW,
    )
    return evaluate_market(
        metrics(), VideoFormat.LONG, references(), synthetic=True, advertising=assessment, **changes
    )


def test_absent_income_not_zero_and_optional_weight_coverage() -> None:
    result = market_for(None)
    assert result.components["M"] is None
    assert result.score is not None
    assert result.weight_coverage == pytest.approx(0.75)
    assert result.missing == ("T", "M")
    zero = market_for(benchmark(rate={"low": 0, "high": 0}))
    assert zero.components["M"] == 0
    assert zero.weight_coverage == pytest.approx(0.85)
    assert zero.score != result.score


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"audience_geography": None}, "audience_geography_unknown"),
        ({"geography_basis": "unknown"}, "audience_geography_unknown"),
        ({"geography_evidence": None}, "audience_geography_unknown"),
        ({"usage": "pending"}, "usage_not_enabled"),
        ({"usage": "disabled"}, "usage_not_enabled"),
        ({"usage_evidence": None}, "usage_not_enabled"),
        ({"audience_key": "other-audience"}, "scope_mismatch"),
        ({"language": "es"}, "scope_mismatch"),
        ({"observed_at": NOW + timedelta(days=1)}, "benchmark_not_current"),
        ({"observed_at": NOW - timedelta(days=2), "valid_until": NOW}, "benchmark_not_current"),
    ],
)
def test_unknown_geo_or_unusable_evidence_never_enters_score(
    change: dict[str, Any], reason: str
) -> None:
    ad = benchmark(**change)
    assessment = assess_advertising(
        ad,
        format=VideoFormat.LONG,
        language="en",
        audience_key="english-content-viewers",
        synthetic=True,
        now=NOW,
    )
    assert reason in assessment.reasons
    assert assessment.scoring_value is None
    assert market_for(ad).components["M"] is None


def test_documented_assumption_uses_lower_range_and_stays_provisional() -> None:
    result = market_for(benchmark(), relevance_reviewed=True)
    assert result.components["M"] == pytest.approx(normalize(2, 10))
    assert result.confidence == "provisional"
    assert result.components["D"] is not None
    assert result.components["B"] is not None
    assert result.components["C"] is not None
    assert result.score == pytest.approx(
        (
            0.25 * result.components["D"]
            + 0.30 * result.components["B"]
            + 0.20 * result.components["C"]
            + 0.10 * normalize(2, 10)
        )
        / 0.85
    )
    assert result == market_for(benchmark(), relevance_reviewed=True)


def test_short_units_and_reference_geography_cannot_be_mixed() -> None:
    with pytest.raises(ValidationError):
        benchmark(format="shorts")
    short = benchmark(format="shorts", unit="usd_ads_per_1000_engaged_views")
    assessment = assess_advertising(
        short,
        format=VideoFormat.SHORTS,
        language="en",
        audience_key="english-content-viewers",
        synthetic=True,
        now=NOW,
    )
    short_metrics = metrics().model_copy(update={"format": VideoFormat.SHORTS})
    assert (
        evaluate_market(
            short_metrics,
            VideoFormat.SHORTS,
            references(format="shorts"),
            synthetic=True,
            advertising=assessment,
        ).components["M"]
        is None
    )
    good_refs = references(format="shorts", monetization_unit="usd_ads_per_1000_engaged_views")
    result = evaluate_market(
        short_metrics, VideoFormat.SHORTS, good_refs, synthetic=True, advertising=assessment
    )
    assert result.components["M"] == pytest.approx(normalize(2, 10))
    other_geo = good_refs.model_copy(update={"monetization_geography": "another-region"})
    assert (
        evaluate_market(
            short_metrics, VideoFormat.SHORTS, other_geo, synthetic=True, advertising=assessment
        ).components["M"]
        is None
    )


@pytest.mark.parametrize(
    "change",
    [
        {"source": "  "},
        {"assumptions": ""},
        {"rate": {"low": 6, "high": 2}},
        {"rate": {"low": "NaN", "high": 6}},
        {"rate": {"low": "1e999", "high": "1e999"}},
        {"unit": "CPM"},
        {"revenue_scope": "total_rpm"},
        {"format": "unknown"},
        {"monetization": "active"},
        {"competitor_rpm": 20},
    ],
)
def test_invalid_economic_inputs_are_rejected(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        benchmark(**change)


def test_new_channel_no_projected_payout_and_synthetic_cannot_score_live() -> None:
    ad = benchmark()
    result = assess_advertising(
        ad,
        format=VideoFormat.LONG,
        language="en",
        audience_key="english-content-viewers",
        synthetic=True,
        now=NOW,
    )
    assert result.projected_payout_usd is None
    assert result.income_condition == "conditional_on_eligibility_activation_and_eligible_views"
    assert result.benchmark is not None
    assert result.benchmark.monetization == "new_channel"
    live = assess_advertising(
        ad,
        format=VideoFormat.LONG,
        language="en",
        audience_key="english-content-viewers",
        synthetic=False,
        now=NOW,
    )
    assert live.scoring_value is None
    assert "synthetic_benchmark_for_live" in live.reasons
    assert (
        evaluate_market(
            metrics(), VideoFormat.LONG, references(), synthetic=False, advertising=result
        ).score
        is None
    )
    real_refs = references(synthetic=False)
    assert (
        evaluate_market(
            metrics(), VideoFormat.LONG, real_refs, synthetic=False, advertising=result
        ).components["M"]
        is None
    )


def test_confidence_requires_complete_components_and_relevance_review() -> None:
    ad = benchmark(origin="own_analytics", geography_basis="observed")
    assessment = assess_advertising(
        ad,
        format=VideoFormat.LONG,
        language="en",
        audience_key="english-content-viewers",
        synthetic=False,
        now=NOW,
    )
    complete = metrics().model_copy(update={"trend_relative_change": 0.5})
    result = evaluate_market(
        complete,
        VideoFormat.LONG,
        references(synthetic=False),
        synthetic=False,
        advertising=assessment,
        relevance_reviewed=True,
    )
    assert result.confidence == "supported"
    assert result.weight_coverage == 1
    assert result.state == "ready_for_review"
    unchecked = evaluate_market(
        complete,
        VideoFormat.LONG,
        references(synthetic=False),
        synthetic=False,
        advertising=assessment,
    )
    assert unchecked.score == result.score
    assert unchecked.confidence == "provisional"


def test_combined_score_requires_both_and_never_overrides_resources() -> None:
    market = market_for(benchmark())
    production = evaluate_plan(complete_plan(), CreatorProfile())
    combined = combine(market, production)
    assert market.score is not None
    assert combined.score == pytest.approx(0.65 * market.score + 0.35 * 75)
    assert combined.confidence == "provisional"
    assert "production_reviews_pending" in combined.blockers
    assert combined.execution_authorized is False
    assert combine(market, None).score is None
    uncalibrated = evaluate_market(metrics(), VideoFormat.LONG, None, synthetic=True)
    assert combine(uncalibrated, production).score is None
    assert combine(uncalibrated, production).state == "uncalibrated"
    high = market.model_copy(
        update={"score": 100, "state": "ready_for_review", "confidence": "supported"}
    )
    over_budget = evaluate_plan(
        complete_plan().model_copy(update={"videos_per_month": 100}), CreatorProfile()
    )
    combined = combine(high, over_budget)
    assert combined.score is not None
    assert combined.score > 90
    assert combined.resource_gate == "not_viable"
    assert set(combined.blockers) >= {
        "resource:monthly_usd",
        "resource:monthly_hours",
        "resource:voice:capacity",
    }
    assert combined.execution_authorized is False
    with pytest.raises(ValueError):
        final_score(high, Decimal("NaN"))


@pytest.mark.postgres
def test_scoring_api_version_worker_snapshot_and_retention(isolated_engine: Engine) -> None:
    provider = SyntheticProvider()
    assert run_pipeline(isolated_engine, NOW, provider)["status"] == "succeeded"
    client = TestClient(
        create_app(
            Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine, clock=lambda: NOW
        )
    )
    with isolated_engine.connect() as connection:
        opportunity = connection.execute(
            select(s.opportunities.c.id).where(s.opportunities.c.format == "long")
        ).scalar_one()
    path = f"/api/v1/opportunities/{opportunity}/scoring"
    assert client.get(path).status_code == 401
    assert client.post(path, json={}).status_code == 401
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    assert client.get(path).json()["advertising"]["status"] == "unavailable"
    configuration = ScoringConfiguration(
        format=VideoFormat.LONG,
        language="en",
        audience_key="english-content-viewers",
        references=references(),
        advertising=benchmark(),
        relevance_review="synthetic review",
        retention_basis="original synthetic fixtures",
        retain_until=NOW + timedelta(days=10),
    )
    payload: dict[str, Any] = {
        "configuration": configuration.model_dump(mode="json"),
        "expected_version": 0,
    }
    before = client.get("/api/v1/consumption").json()
    assert client.post(path, json=payload).status_code == 201
    assert client.post(path, json=payload).status_code == 409
    assert client.get(path).json()["configuration"] == configuration.model_dump(mode="json")
    bad = configuration.model_dump(mode="json") | {"audience_key": "other", "advertising": None}
    assert client.post(path, json={"configuration": bad, "expected_version": 1}).status_code == 422
    # The default recipe auto-applies during the worker's evaluation stage, so this
    # opportunity already carries version 1 before any manual assignment.
    assert (
        client.post(
            f"/api/v1/opportunities/{opportunity}/production",
            json={"plan": complete_plan().model_dump(mode="json"), "expected_version": 1},
        ).status_code
        == 201
    )
    assert client.get("/api/v1/consumption").json() == before
    assert (
        client.post(
            f"/api/v1/opportunities/{opportunity}/decisions",
            json={"state": "selected", "note": "Research only", "expected_version": 0},
        ).status_code
        == 200
    )
    assert run_pipeline(isolated_engine, NOW + timedelta(days=2), provider)["status"] == "succeeded"
    with isolated_engine.connect() as connection:
        evaluations = (
            connection.execute(
                select(s.evaluation_versions)
                .where(s.evaluation_versions.c.opportunity_id == opportunity)
                .order_by(s.evaluation_versions.c.version)
            )
            .mappings()
            .all()
        )
        previous, latest = evaluations[0], evaluations[-1]
        assert previous["market_score"] is None and previous["final_score"] is None
        assert latest["market_score"] is not None
        assert float(latest["final_score"]) == pytest.approx(
            0.65 * float(latest["market_score"]) + 0.35 * 75
        )
        assert latest["retain_until"] <= configuration.retain_until
        assert latest["explanation"]["advertising"]["benchmark"]["rate"] == {
            "low": "2",
            "high": "6",
        }
        assert latest["explanation"]["combined"]["execution_authorized"] is False
        component = connection.execute(
            select(s.feature_values.c.value).where(
                s.feature_values.c.evaluation_id == latest["id"], s.feature_values.c.name == "M"
            )
        ).scalar_one()
        assert float(component) == pytest.approx(normalize(2, 10))
    payload["expected_version"] = 1
    payload["configuration"]["advertising"] = None
    assert client.post(path, json=payload).status_code == 201
    with isolated_engine.connect() as connection:
        stored = connection.execute(
            select(s.evaluation_versions.c.explanation).where(
                s.evaluation_versions.c.id == latest["id"]
            )
        ).scalar_one()
        assert stored == latest["explanation"]
    with isolated_engine.begin() as connection:
        expire(connection, NOW + timedelta(days=11))
        rows = connection.execute(select(opportunity_scoring_configs)).mappings().all()
        assert len(rows) == 2
        assert all(row["configuration"] is None and row["expired_at"] is not None for row in rows)
        expired = (
            connection.execute(
                select(s.evaluation_versions).where(s.evaluation_versions.c.id == latest["id"])
            )
            .mappings()
            .one()
        )
        assert expired["explanation"] is None and expired["final_score"] is None
        assert expired["market_score"] is None
    assert client.get(path).json()["expired"] is True
    assert client.get(path).json()["version"] == 2
    assert client.get(path).json()["configuration"] is None
    assert (
        client.get(f"/api/v1/opportunities/{opportunity}").json()["decision"]["state"] == "selected"
    )
