"""Sufijos en español/portugués y motivo registrado de cada entrada descartada."""

from decimal import Decimal
from typing import Any

import pytest

from nicheradar.market_intel.evidence.contracts import ModelEvidence
from nicheradar.market_intel.evidence.reconcile import (
    drop_unverifiable_entries,
    raw_text_matches,
)
from nicheradar.market_intel.evidence.tolerant import tolerant_evidence
from tests.test_market_intel_evidence import base


@pytest.mark.parametrize(
    ("raw", "value"),
    [
        ("69,7 mil", 69700),
        ("1,2 mill.", 1_200_000),
        ("1,2 millones", 1_200_000),
        ("5 mil", 5000),
        ("US$ 1.276,14", Decimal("1276.14")),
        ("69.7K", 69700),
        ("1.2M", 1_200_000),
    ],
)
def test_raw_text_in_spanish_or_portuguese_reproduces_the_value(
    raw: str, value: float | Decimal
) -> None:
    assert raw_text_matches(raw, value)


def test_a_unit_word_is_not_read_as_a_multiplier() -> None:
    assert not raw_text_matches("5 milagros", 5000)
    assert raw_text_matches("5 milagros", 5)


def evidence_with(**changes: Any) -> ModelEvidence:
    doc = base()
    for block, fields in changes.items():
        doc[block][0].update(fields)
    return ModelEvidence.model_validate(doc)


def test_a_dropped_view_records_what_the_text_said_and_what_the_model_reported() -> None:
    evidence = evidence_with(views={"raw_text": "97.6K"})
    kept = drop_unverifiable_entries(evidence)
    [gap] = kept.unresolved
    assert gap.note is not None and "97.6K" in gap.note and "69700" in gap.note


def test_a_dropped_period_records_the_kind_and_which_dates_are_missing() -> None:
    doc = base()
    doc["views"][0]["period"] = {"kind": "calendar_month", "start": None, "end": None}
    [gap] = tolerant_evidence(doc).unresolved
    assert gap.reason == "ambiguous_period"
    assert gap.note is not None and "calendar_month" in gap.note and "no dates" in gap.note


def test_a_dropped_entry_records_the_first_failing_field() -> None:
    doc = base()
    doc["earnings"][0]["raw_text"] = "x" * 200
    [gap] = tolerant_evidence(doc).unresolved
    assert gap.note is not None and "raw_text" in gap.note


@pytest.mark.parametrize(
    ("raw", "value"),
    [
        ("US$0.001", Decimal("0.001")),
        ("$0.005", Decimal("0.005")),
        ("0,001", Decimal("0.001")),
        ("US$0.83", Decimal("0.83")),
    ],
)
def test_a_number_starting_with_zero_and_a_separator_is_a_decimal_never_thousands(
    raw: str, value: Decimal
) -> None:
    assert raw_text_matches(raw, value)


@pytest.mark.parametrize(("raw", "value"), [("US$0.001", 1), ("$0.005", 5)])
def test_a_sub_unit_amount_is_not_read_as_a_whole_number(raw: str, value: int) -> None:
    assert not raw_text_matches(raw, value)


def test_thousands_separators_still_work() -> None:
    cases: list[tuple[str, int | Decimal]] = [
        ("1,276", 1276),
        ("1.001", 1001),
        ("US$1.276,14", Decimal("1276.14")),
    ]
    for raw, value in cases:
        assert raw_text_matches(raw, value)


def test_the_scale_correction_does_not_inflate_a_correct_sub_cent_amount() -> None:
    doc = base()
    doc["earnings"][0]["raw_text"] = "US$0.001"
    doc["earnings"][0]["amount"]["value"] = "0.001"
    evidence = drop_unverifiable_entries(ModelEvidence.model_validate(doc))
    assert evidence.earnings[0].amount.value == Decimal("0.001")
