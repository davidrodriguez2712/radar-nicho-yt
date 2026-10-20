# tests/test_market_intel_scoring.py
import math

import pytest

from nicheradar.market_intel.scoring import (
    AUTOMATION_WEIGHTS,
    MINIMUM_INCOME_LISTINGS,
    ListingFacts,
    automation_score,
    confidence,
    log_scale,
    niche_metrics,
    opportunity_score,
    outlier_mask,
)

NO_TRAITS: dict[str, int | None] = {}


def facts(
    income: float | None,
    *,
    subscribers: int | None = 20_000,
    price: float | None = 12_000,
    expense: float | None = None,
    status: str = "active",
    verification: str | None = None,
    days: int = 1,
) -> ListingFacts:
    return ListingFacts(
        status=status,
        price_usd=price,
        subscribers=subscribers,
        income_usd=income,
        expense_usd=expense,
        verification=verification,
        days_since_seen=days,
        traits=NO_TRAITS,
    )


def test_log_scale_anchors() -> None:
    assert log_scale(50, 50, 3000) == pytest.approx(0)
    assert log_scale(3000, 50, 3000) == pytest.approx(100)
    assert log_scale(math.sqrt(50 * 3000), 50, 3000) == pytest.approx(50)
    assert log_scale(1, 50, 3000) == 0 and log_scale(10**6, 50, 3000) == 100
    assert log_scale(0, 50, 3000) is None and log_scale(None, 50, 3000) is None


def test_outlier_mask_flags_only_extreme_values() -> None:
    assert outlier_mask([5, 5.2, 4.8, 5.1, 4.9, 60]) == [False] * 5 + [True]
    assert outlier_mask([5, 60, 7]) == [False, False, False]  # too few samples to judge
    assert outlier_mask([5, 5, 5, 5, 5, 5]) == [False] * 6  # MAD of zero


def test_zero_or_missing_income_is_not_evidence() -> None:
    metrics = niche_metrics([facts(0.0), facts(None), facts(300), facts(400), facts(500)])
    assert metrics["n_listings"] == 5 and metrics["n_income"] == 3
    assert metrics["income_median"] == 400


def test_mismatched_or_missing_channels_are_excluded_from_income_statistics() -> None:
    metrics = niche_metrics(
        [
            facts(300, verification="verified"),
            facts(400, verification="mismatch"),
            facts(500, verification="not_found"),
            facts(600),
        ]
    )
    assert metrics["n_income"] == 2 and metrics["verified_share"] == 0.5


def test_metrics_medians_margin_multiple_and_dynamics() -> None:
    metrics = niche_metrics(
        [
            facts(1000, expense=200, price=24_000, subscribers=50_000),
            facts(1200, expense=0, price=36_000, subscribers=60_000, status="disappeared"),
            facts(800, expense=400, price=19_200, subscribers=40_000),
            facts(None, status="disappeared"),
        ]
    )
    assert metrics["income_median"] == 1000
    assert metrics["margin_median"] == pytest.approx(0.8)
    assert metrics["multiple_median"] == pytest.approx(2.0 * 12 / 12)  # 24000 / (1000 * 12)
    assert metrics["income_per_1k_subs_median"] == pytest.approx(20.0)
    assert metrics["n_active"] == 2 and metrics["disappearance_rate"] == 0.5


def test_outlier_income_per_subscriber_is_dropped() -> None:
    rows = [facts(100, subscribers=20_000 + step) for step in range(0, 500, 100)]
    rows.append(facts(5000, subscribers=1_000))
    metrics = niche_metrics(rows)
    assert metrics["n_outliers"] == 1 and metrics["n_income"] == 5


def rich() -> list[ListingFacts]:
    return [
        facts(income, expense=income * 0.1, price=income * 12 * 2.5)
        for income in (1500, 2000, 2500, 3000)
    ]


def poor() -> list[ListingFacts]:
    return [
        facts(income, expense=income * 0.8, price=income * 12 * 0.67)
        for income in (60, 80, 100, 120)
    ]


def test_insufficient_evidence_below_three_income_listings() -> None:
    few = niche_metrics([facts(500), facts(600), facts(None)])
    assert few["n_income"] < MINIMUM_INCOME_LISTINGS
    result = opportunity_score(few, None)
    assert result["value"] is None and result["state"] == "insufficient_evidence"
    assert result["components_used"] == [] and confidence(few) == "baja"


def test_richer_niche_scores_higher_and_rpm_only_helps_when_known() -> None:
    top = opportunity_score(niche_metrics(rich()), None)
    bottom = opportunity_score(niche_metrics(poor()), None)
    assert top["state"] == "scored" and 0 <= bottom["value"] < top["value"] <= 100
    assert set(top["components_used"]) == {"profitability", "efficiency", "validation", "dynamics"}
    with_rpm = opportunity_score(niche_metrics(poor()), 11.0)
    assert with_rpm["value"] > bottom["value"]
    assert with_rpm["components"]["efficiency"] > bottom["components"]["efficiency"]


def test_confidence_levels() -> None:
    many = niche_metrics([facts(500 + step, verification="verified") for step in range(10)])
    assert confidence(many) == "alta"
    some = niche_metrics([facts(500 + step, days=60) for step in range(5)])
    assert confidence(some) == "baja"
    middling = niche_metrics(
        [facts(500 + step, verification="verified", days=60) for step in range(3)]
    )
    assert confidence(middling) == "media"  # 0.15 + 0.30 + 0.00 = 0.45


def test_automation_weights_and_boundaries() -> None:
    assert sum(AUTOMATION_WEIGHTS.values()) == 100
    full: dict[str, int | None] = dict.fromkeys(AUTOMATION_WEIGHTS, 2)
    assert automation_score([full], None)["value"] == 100
    empty: dict[str, int | None] = dict.fromkeys(AUTOMATION_WEIGHTS, 0)
    assert automation_score([empty], None)["value"] == 0
    only_faceless: dict[str, int | None] = {**empty, "faceless": 2}
    assert automation_score([only_faceless], None)["value"] == 30


def test_automation_falls_back_to_the_niche_prior_and_needs_three_traits() -> None:
    prior: dict[str, int | None] = dict.fromkeys(AUTOMATION_WEIGHTS, 2)
    blank: dict[str, int | None] = dict.fromkeys(AUTOMATION_WEIGHTS)
    assert automation_score([blank], prior)["value"] == 100
    assert automation_score([blank], None)["value"] is None
    two_only: dict[str, int | None] = {**blank, "faceless": 2, "scriptable": 2}
    assert automation_score([two_only], None)["value"] is None
    assert automation_score([], prior)["value"] == 100


@pytest.mark.parametrize(("risk", "level"), [(0, "bajo"), (1, "medio"), (2, "alto")])
def test_policy_risk_is_reported_separately_and_never_subtracted(risk: int, level: str) -> None:
    traits: dict[str, int | None] = {**dict.fromkeys(AUTOMATION_WEIGHTS, 2), "policy_risk": risk}
    result = automation_score([traits], None)
    assert result["value"] == 100
    assert result["policy_risk"] == {"mean": float(risk), "level": level}
