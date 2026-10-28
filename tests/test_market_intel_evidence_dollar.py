"""D9: `$` sin código ISO es USD solo con interfaz en inglés; corrección de escala de raw_text."""

from copy import deepcopy
from decimal import Decimal
from typing import Any

import pytest

from nicheradar.market_intel.evidence.contracts import ModelEvidence
from nicheradar.market_intel.evidence.derive import (
    grade,
    observation_sets,
    rpm_sample_eligible,
    select_primary,
)
from nicheradar.market_intel.evidence.reconcile import drop_unverifiable_entries
from nicheradar.market_intel.evidence.summary import build_derived
from nicheradar.market_intel.evidence.tolerant import tolerant_evidence
from nicheradar.market_intel.evidence.wire import evidence_schema
from tests.test_market_intel_evidence import NOW, TODAY, base


def with_symbol(language: str | None, currency: str = "$") -> dict[str, Any]:
    doc = deepcopy(base())
    doc["images"][0]["ui_language"] = language
    doc["earnings"][0]["amount"]["currency"] = currency
    return doc


@pytest.mark.parametrize("language", ["en", "en-US", "English"])
def test_a_bare_dollar_with_an_english_interface_is_usd_and_remembered(language: str) -> None:
    evidence = tolerant_evidence(with_symbol(language))
    assert evidence.earnings[0].amount.currency == "USD"
    assert evidence.usd_symbol_images == (0,) and evidence.unresolved == ()


@pytest.mark.parametrize("language", ["es", "pt-BR", "Español", None])
def test_a_bare_dollar_with_another_or_unknown_interface_is_dropped_as_ambiguous(
    language: str | None,
) -> None:
    evidence = tolerant_evidence(with_symbol(language))
    assert evidence.earnings == () and evidence.usd_symbol_images == ()
    [gap] = evidence.unresolved
    assert (gap.topic, gap.reason, gap.image_index) == ("revenue", "ambiguous_currency", 0)
    assert gap.note is not None and "$" in gap.note


def test_a_dollar_with_an_explicit_prefix_needs_no_assumption() -> None:
    evidence = tolerant_evidence(with_symbol("es", "US$"))
    assert evidence.earnings[0].amount.currency == "USD" and evidence.usd_symbol_images == ()


def test_the_model_cannot_declare_its_own_assumptions() -> None:
    doc = with_symbol("es", "USD")
    doc["usd_symbol_images"] = [0]
    assert tolerant_evidence(doc).usd_symbol_images == ()


def test_the_assumption_field_is_code_owned_and_never_asked_of_the_model() -> None:
    assert "usd_symbol_images" not in evidence_schema()["properties"]
    assert "usd_symbol_images" not in evidence_schema()["required"]


def test_an_assumed_usd_set_caps_the_grade_at_b_and_is_not_an_rpm_sample() -> None:
    evidence = tolerant_evidence(with_symbol("en"))
    sets = observation_sets(evidence, {}, TODAY)
    primary = select_primary(sets)
    verdict = grade(evidence, primary, sets, has_api_views=False)
    assert verdict == "B"
    assert rpm_sample_eligible(primary, evidence, verdict) is False
    clean = ModelEvidence.model_validate(base())
    clean_sets = observation_sets(clean, {}, TODAY)
    assert grade(clean, select_primary(clean_sets), clean_sets, has_api_views=False) == "A"


def test_the_derived_block_carries_a_low_currency_assumed_usd_flag() -> None:
    derived = build_derived(
        tolerant_evidence(with_symbol("en")), fx={}, extracted_at=NOW, declared_income=None
    )
    flags = [(f["code"], f["severity"]) for f in derived["risk_flags"]]
    assert ("currency_assumed_usd", "low") in flags
    assert derived["rpm_sample_eligible"] is False


def test_a_rate_with_an_unusable_currency_is_kept_without_it() -> None:
    doc = with_symbol("es")
    doc["rates"] = [
        {
            "image_index": 0,
            "metric": "rpm",
            "scope": "all",
            "period": doc["views"][0]["period"],
            "value": 4.2,
            "currency": "$",
            "raw_text": "$4.20",
            "legibility": "clear",
        }
    ]
    evidence = tolerant_evidence(doc)
    assert evidence.rates[0].currency is None


def evidence_with_view(raw: str, value: float) -> ModelEvidence:
    doc = deepcopy(base())
    doc["views"][0].update({"raw_text": raw, "value": value})
    return drop_unverifiable_entries(ModelEvidence.model_validate(doc))


@pytest.mark.parametrize(
    ("raw", "value", "expected"),
    [("100K", 100.0, 100_000), ("10,2M", 10.2, 10_200_000), ("313,5K", 313.5, 313_500)],
)
def test_a_value_missing_the_texts_multiplier_is_taken_from_the_text(
    raw: str, value: float, expected: int
) -> None:
    evidence = evidence_with_view(raw, value)
    assert evidence.views[0].value == expected and evidence.unresolved == ()


@pytest.mark.parametrize(("raw", "value"), [("5 050 504,8", 5058504.8), ("3.3L", 331791.0)])
def test_a_misread_number_is_still_dropped(raw: str, value: float) -> None:
    evidence = evidence_with_view(raw, value)
    assert evidence.views == () and len(evidence.unresolved) == 1


def test_an_earning_missing_the_multiplier_is_corrected_too() -> None:
    doc = deepcopy(base())
    doc["earnings"][0]["raw_text"] = "$5.3K"
    doc["earnings"][0]["amount"]["value"] = "5.3"
    evidence = drop_unverifiable_entries(ModelEvidence.model_validate(doc))
    assert evidence.earnings[0].amount.value == Decimal("5300")
