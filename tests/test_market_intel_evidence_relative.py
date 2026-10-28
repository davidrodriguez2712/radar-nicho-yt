"""Decisión D8: periodos relativos (`last_28d`...) sin fechas visibles son válidos."""

from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from nicheradar.market_intel.evidence.contracts import ModelEvidence
from nicheradar.market_intel.evidence.derive import (
    grade,
    observation_sets,
    rpm_sample_eligible,
    select_primary,
)
from nicheradar.market_intel.evidence.summary import build_derived
from nicheradar.market_intel.evidence.tolerant import tolerant_evidence
from tests.test_market_intel_evidence import NOW, TODAY, base


def undated(kind: str = "last_28d") -> dict[str, Any]:
    return {"kind": kind, "start": None, "end": None}


def mobile_dashboard(*, captured_on: str | None = None, kind: str = "last_28d") -> dict[str, Any]:
    """Studio móvil: «Last 28 days», visitas e ingreso, sin fechas ni fecha de captura."""
    doc = deepcopy(base())
    doc["images"][0]["captured_on"] = captured_on
    doc["images"][0]["captured_on_basis"] = "visible_in_image" if captured_on else "unknown"
    doc["earnings"][0]["period"] = undated(kind)
    doc["views"][0]["period"] = undated(kind)
    return doc


@pytest.mark.parametrize("kind", ["last_7d", "last_28d", "last_90d", "last_365d"])
def test_a_relative_period_may_have_no_dates(kind: str) -> None:
    evidence = ModelEvidence.model_validate(mobile_dashboard(kind=kind))
    assert evidence.earnings[0].period.start is None


@pytest.mark.parametrize("kind", ["calendar_month", "custom"])
def test_a_calendar_or_custom_period_still_needs_dates(kind: str) -> None:
    doc = mobile_dashboard()
    doc["earnings"][0]["period"] = undated(kind)
    with pytest.raises(ValidationError, match="period_dates_required"):
        ModelEvidence.model_validate(doc)


def test_a_period_with_only_one_date_is_still_rejected() -> None:
    doc = mobile_dashboard()
    doc["earnings"][0]["period"] = {"kind": "last_28d", "start": "2026-10-01", "end": None}
    with pytest.raises(ValidationError, match="period_dates_incomplete"):
        ModelEvidence.model_validate(doc)


def test_an_undated_window_counts_its_nominal_days() -> None:
    [found] = observation_sets(ModelEvidence.model_validate(mobile_dashboard()), {}, TODAY)
    assert found.days == 28 and found.period.start is None
    assert found.monthly_revenue_usd is not None


def test_undated_measures_pair_only_inside_the_same_capture() -> None:
    doc = mobile_dashboard()
    doc["images"].append({**doc["images"][0], "index": 1})
    doc["views"][0]["image_index"] = 1
    assert observation_sets(ModelEvidence.model_validate(doc), {}, TODAY) == ()


def test_undated_measures_of_different_kinds_do_not_pair() -> None:
    doc = mobile_dashboard()
    doc["views"][0]["period"] = undated("last_90d")
    assert observation_sets(ModelEvidence.model_validate(doc), {}, TODAY) == ()


def test_a_dated_and_an_undated_measure_do_not_pair() -> None:
    doc = mobile_dashboard()
    doc["views"][0]["period"] = {"kind": "last_28d", "start": "2026-09-29", "end": "2026-10-26"}
    assert observation_sets(ModelEvidence.model_validate(doc), {}, TODAY) == ()


def test_without_a_visible_capture_date_the_grade_is_capped_at_c_and_no_rpm_sample() -> None:
    evidence = ModelEvidence.model_validate(mobile_dashboard())
    sets = observation_sets(evidence, {}, TODAY)
    primary = select_primary(sets)
    assert primary is not None and primary.capture_age_days is None
    verdict = grade(evidence, primary, sets, has_api_views=False)
    assert verdict == "C"
    assert rpm_sample_eligible(primary, evidence, verdict) is False


def test_with_a_visible_capture_date_the_window_can_reach_grade_a() -> None:
    evidence = ModelEvidence.model_validate(mobile_dashboard(captured_on="2026-10-26"))
    sets = observation_sets(evidence, {}, TODAY)
    primary = select_primary(sets)
    assert primary is not None and primary.capture_age_days == 2
    assert grade(evidence, primary, sets, has_api_views=False) == "A"


def test_the_derived_block_marks_undated_windows_and_yields_income_and_rpm() -> None:
    derived = build_derived(
        ModelEvidence.model_validate(mobile_dashboard()),
        fx={},
        extracted_at=NOW,
        declared_income=None,
    )
    assert derived["income_level"] == "L1"
    assert derived["primary"]["dates_visible"] is False
    assert derived["observed_monthly_income_usd"] is not None and derived["rpm_usd"] is not None
    assert derived["evidence_grade"] == "C" and derived["rpm_sample_eligible"] is False


def test_the_dated_window_is_marked_as_dated() -> None:
    derived = build_derived(
        ModelEvidence.model_validate(base()), fx={}, extracted_at=NOW, declared_income=None
    )
    assert derived["primary"]["dates_visible"] is True


def test_the_tolerant_parser_keeps_undated_relative_entries_and_drops_undated_months() -> None:
    doc = mobile_dashboard()
    doc["views"].append({**doc["views"][0], "period": undated("calendar_month")})
    evidence = tolerant_evidence(doc)
    assert len(evidence.views) == 1 and len(evidence.earnings) == 1
    assert [(u.topic, u.reason) for u in evidence.unresolved] == [("views", "ambiguous_period")]
