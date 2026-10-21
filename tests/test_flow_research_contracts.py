# tests/test_flow_research_contracts.py
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from nicheradar.flow_research.contracts import validate_dossier
from tests.flow_research_samples import valid_dossier

NOW = datetime(2026, 10, 20, 15, tzinfo=UTC)
REQUEST = UUID("00000000-0000-4000-8000-000000000001")


def put(payload: dict[str, Any], dotted: str, value: Any) -> dict[str, Any]:
    *parents, last = dotted.split(".")
    target: Any = payload
    for part in parents:
        target = target[int(part)] if part.isdigit() else target[part]
    if last.isdigit():
        target[int(last)] = value
    else:
        target[last] = value
    return payload


def found_paths(payload: dict[str, Any]) -> set[str]:
    dossier, problems = validate_dossier(payload, NOW)
    assert dossier is None
    return {problem["path"] for problem in problems}


def test_a_complete_dossier_is_accepted() -> None:
    dossier, problems = validate_dossier(valid_dossier(REQUEST, NOW), NOW)
    assert problems == [] and dossier is not None
    assert dossier.budget.totals.likely == Decimal("133")
    assert dossier.request_id == REQUEST


def test_no_go_is_a_valid_outcome() -> None:
    payload = put(valid_dossier(REQUEST, NOW), "verdict.recommendation", "no_go")
    assert validate_dossier(payload, NOW)[1] == []


def test_float_noise_in_money_is_tolerated() -> None:
    payload = valid_dossier(REQUEST, NOW)
    put(payload, "budget.lines.1.unit_cost_usd", 3.0)
    put(payload, "budget.lines.1.quantity", 3)
    put(payload, "budget.lines.1.subtotal_usd", 9.000000000000002)
    assert validate_dossier(payload, NOW)[1] == []


CASES = [
    ("surprise", 1, "surprise"),
    ("competitors.0.channel_url", "http://www.youtube.com/@a", "competitors.0.channel_url"),
    ("budget.lines.0.source_id", "zz", "budget.lines.0.source_id"),
    (
        "budget.lines.0.price_checked_on",
        (NOW - timedelta(days=91)).date().isoformat(),
        "budget.lines.0.price_checked_on",
    ),
    (
        "budget.lines.0.price_checked_on",
        (NOW + timedelta(days=1)).date().isoformat(),
        "budget.lines.0.price_checked_on",
    ),
    ("budget.lines.0.subtotal_usd", 41, "budget.lines.0.subtotal_usd"),
    ("roadmap.0.cost_usd", 50, "roadmap.0.cost_usd"),
    ("budget.totals.likely", 140, "budget.totals.likely"),
    ("roadmap.0.exit_criteria", [], "roadmap.0.exit_criteria"),
    ("budget.lines.0.tool", "Otra", "budget.lines.0.tool"),
    ("budget.lines.0.phase", "Otra", "budget.lines.0.phase"),
    ("roadmap.1.weeks", 20, "roadmap"),
    ("generated_at", (NOW - timedelta(days=3)).isoformat(), "generated_at"),
    ("production_flow.1.order", 5, "production_flow"),
    ("competitors", [], "competitors"),
    ("break_even.evidence_kind", "researched", "break_even.evidence_kind"),
    ("sources.1.id", "s1", "sources"),
    ("budget.totals.low", 500, "budget.totals"),
    ("verdict.thesis", "x" * 1501, "verdict.thesis"),
    ("tools.0.phase", "Otra", "tools.0.phase"),
]


@pytest.mark.parametrize(("dotted", "value", "path"), CASES)
def test_each_rule_rejects_its_violation(dotted: str, value: Any, path: str) -> None:
    payload = put(valid_dossier(REQUEST, NOW), dotted, value)
    assert path in found_paths(payload)


def test_validation_errors_never_echo_the_submitted_value() -> None:
    payload = put(valid_dossier(REQUEST, NOW), "verdict.thesis", "SECRET" * 400)
    _, problems = validate_dossier(payload, NOW)
    assert problems and all("SECRET" not in problem["message"] for problem in problems)


def test_a_payload_that_is_not_an_object_is_reported_not_raised() -> None:
    dossier, problems = validate_dossier(["not", "a", "dossier"], NOW)
    assert dossier is None and problems
