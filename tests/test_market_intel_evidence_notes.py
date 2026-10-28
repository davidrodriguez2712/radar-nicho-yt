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
