"""Una entrada mal formada se descarta y se registra; no invalida la respuesta completa."""

import json
from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from nicheradar.market_intel.evidence.tolerant import tolerant_evidence
from nicheradar.market_intel.evidence.wire import parse_response
from tests.test_market_intel_evidence import base
from tests.test_market_intel_evidence_stage import TARIFF, response


def undated(entry: dict[str, Any]) -> dict[str, Any]:
    entry = deepcopy(entry)
    entry["period"] = {"kind": "last_28d", "start": None, "end": None}
    return entry


def test_a_clean_document_is_unchanged() -> None:
    evidence = tolerant_evidence(base())
    assert len(evidence.earnings) == 1 and len(evidence.views) == 1 and evidence.unresolved == ()


def test_an_entry_without_period_dates_is_dropped_as_ambiguous_and_the_rest_survives() -> None:
    doc = base()
    doc["views"].append(undated(doc["views"][0]))
    evidence = tolerant_evidence(doc)
    assert len(evidence.earnings) == 1 and len(evidence.views) == 1
    [gap] = evidence.unresolved
    assert (gap.topic, gap.reason, gap.image_index) == ("views", "ambiguous_period", 0)


def test_a_malformed_earning_is_dropped_as_revenue_unreadable() -> None:
    doc = base()
    doc["earnings"][0]["raw_text"] = "x" * 200
    evidence = tolerant_evidence(doc)
    assert evidence.earnings == ()
    assert [(u.topic, u.reason) for u in evidence.unresolved] == [("revenue", "unreadable")]


def test_a_visible_currency_that_is_not_iso_becomes_unknown_instead_of_failing() -> None:
    doc = base()
    doc["images"][0]["currency_visible"] = "$"
    evidence = tolerant_evidence(doc)
    assert evidence.images[0].currency_visible is None


def test_countries_without_an_iso_code_are_dropped_and_valid_ones_kept() -> None:
    doc = base()
    doc["audience"] = {
        "scope": "channel",
        "period": doc["views"][0]["period"],
        "countries": [{"code": "United States", "pct": 40}, {"code": "US", "pct": 30}],
        "image_index": 0,
    }
    evidence = tolerant_evidence(doc)
    assert evidence.audience is not None
    assert [c.code for c in evidence.audience.countries] == ["US"]
    assert any(u.topic == "audience" for u in evidence.unresolved)


def test_an_audience_without_period_dates_is_kept_without_period() -> None:
    doc = base()
    doc["audience"] = {
        "scope": "channel",
        "period": {"kind": "last_28d", "start": None, "end": None},
        "countries": [{"code": "US", "pct": 60}],
        "image_index": 0,
    }
    evidence = tolerant_evidence(doc)
    assert evidence.audience is not None and evidence.audience.period is None
    assert [(u.topic, u.reason) for u in evidence.unresolved] == [("audience", "ambiguous_period")]


@pytest.mark.parametrize("broken", ["identity_check", "monetization", "images"])
def test_a_broken_required_block_still_rejects_the_document(broken: str) -> None:
    doc = base()
    doc[broken] = {"nonsense": True} if broken != "images" else "nope"
    with pytest.raises(ValidationError):
        tolerant_evidence(doc)


def test_unknown_blocks_are_still_rejected() -> None:
    with pytest.raises(ValidationError):
        tolerant_evidence(base(derived={}))


def test_dropped_entries_never_exceed_the_unresolved_cap() -> None:
    doc = base()
    doc["views"] = [undated(doc["views"][0]) for _ in range(24)]
    evidence = tolerant_evidence(doc)
    assert evidence.views == () and len(evidence.unresolved) == 20


def test_parse_response_keeps_a_response_with_one_bad_entry() -> None:
    doc = base()
    doc["views"].append(undated(doc["views"][0]))
    result = parse_response(response(json.dumps(doc)), TARIFF)
    assert result.reason == "response_received" and result.evidence is not None
    assert len(result.evidence.views) == 1
