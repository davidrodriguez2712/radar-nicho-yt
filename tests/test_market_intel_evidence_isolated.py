"""§6.5: sin pareja ingreso-visitas, el ingreso mensual es el ingreso aislado normalizado."""

from copy import deepcopy
from decimal import Decimal
from typing import Any

import pytest

from nicheradar.market_intel.evidence.contracts import ModelEvidence
from nicheradar.market_intel.evidence.derive import isolated_monthly_revenue
from nicheradar.market_intel.evidence.summary import build_derived
from tests.test_market_intel_evidence import NOW, TODAY, base, period


def revenue_only(**changes: Any) -> dict[str, Any]:
    doc = deepcopy(base())
    doc["views"] = []
    for key, value in changes.items():
        doc["earnings"][0][key] = value
    return doc


def isolated(doc: dict[str, Any]) -> Decimal | None:
    return isolated_monthly_revenue(ModelEvidence.model_validate(doc), {}, TODAY)


def test_a_28_day_revenue_is_normalized_to_a_month() -> None:
    assert isolated(revenue_only()) == Decimal("295.18") * Decimal("30.4375") / 28


def test_an_undated_window_uses_its_nominal_days() -> None:
    undated = {"kind": "last_28d", "start": None, "end": None}
    assert isolated(revenue_only(period=undated)) == Decimal("295.18") * Decimal("30.4375") / 28


def test_the_shorter_window_wins_over_the_longer_one() -> None:
    doc = revenue_only()
    long_year = deepcopy(doc["earnings"][0])
    long_year["period"] = period("last_365d", "2025-10-27", "2026-10-26")
    long_year["amount"]["value"] = "9000.00"
    long_year["raw_text"] = "$9,000.00"
    doc["earnings"].append(long_year)
    assert isolated(doc) == Decimal("295.18") * Decimal("30.4375") / 28


@pytest.mark.parametrize("scope", ["shorts", "live", "other"])
def test_only_channel_wide_or_long_form_revenue_counts(scope: str) -> None:
    assert isolated(revenue_only(scope=scope)) is None


def test_a_lifetime_revenue_cannot_be_normalized() -> None:
    assert isolated(revenue_only(period={"kind": "lifetime"})) is None


def test_a_non_revenue_metric_does_not_count() -> None:
    assert isolated(revenue_only(metric="membership_revenue")) is None


def test_a_foreign_currency_without_a_rate_is_skipped() -> None:
    doc = revenue_only()
    doc["earnings"][0]["amount"]["currency"] = "EUR"
    assert isolated(doc) is None


def test_the_derived_block_reports_l2_with_the_normalized_income_and_the_ratio() -> None:
    derived = build_derived(
        ModelEvidence.model_validate(revenue_only()),
        fx={},
        extracted_at=NOW,
        declared_income=Decimal("1000"),
    )
    assert derived["income_level"] == "L2"
    assert derived["observed_monthly_income_usd"] == "320.88"
    assert derived["declared_vs_observed_ratio"] == pytest.approx(0.32088, abs=1e-4)
    assert derived["primary"] is None and derived["rpm_sample_eligible"] is False


def test_l2_without_a_normalizable_revenue_keeps_no_income() -> None:
    derived = build_derived(
        ModelEvidence.model_validate(revenue_only(scope="shorts")),
        fx={},
        extracted_at=NOW,
        declared_income=Decimal("1000"),
    )
    assert derived["income_level"] == "L2" and derived["observed_monthly_income_usd"] is None


def test_a_paired_set_still_wins_and_stays_l1() -> None:
    derived = build_derived(
        ModelEvidence.model_validate(base()), fx={}, extracted_at=NOW, declared_income=None
    )
    assert derived["income_level"] == "L1" and derived["primary"] is not None
