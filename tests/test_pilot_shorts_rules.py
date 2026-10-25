# tests/test_pilot_shorts_rules.py
"""Reglas de parada por formato: Shorts usa sus métricas (bench de Shorts), no las del largo."""

from typing import Any

import pytest

from nicheradar.pilots.contracts import validate_package, with_sha256
from nicheradar.pilots.rules import NOT_EVALUABLE, evaluate
from nicheradar.pilots.service import default_stop_rules
from tests.pilot_samples import NOW, package_body
from tests.test_pilot_rules import vid

SHORTS_METRICS = ["engaged_view_ratio_pct", "avg_view_pct", "shorts_feed_share_pct"]


def shorts_body(metric: str, format: str = "shorts") -> dict[str, Any]:
    body = package_body()
    body["niche"]["format"] = format
    body["stop_rules"] = [
        {
            "id": "regla-1",
            "text": "Regla de prueba",
            "metric": metric,
            "comparator": ">=",
            "threshold": 50,
            "min_cases": 3,
            "milestone": {"kind": "video", "value": 10},
        }
    ]
    return body


@pytest.mark.parametrize("metric", SHORTS_METRICS)
def test_a_shorts_package_accepts_the_shorts_metrics(metric: str) -> None:
    parsed, problems = validate_package(with_sha256(shorts_body(metric)), NOW)
    assert problems == [] and parsed is not None


@pytest.mark.parametrize("metric", SHORTS_METRICS)
def test_a_long_package_rejects_the_shorts_metrics(metric: str) -> None:
    _, problems = validate_package(with_sha256(shorts_body(metric, "long")), NOW)
    assert {"path": "stop_rules.0.metric", "message": "no corresponde al formato long"} in problems


@pytest.mark.parametrize("metric", ["avd_pct", "browse_share_pct"])
def test_a_shorts_package_rejects_the_long_form_metrics(metric: str) -> None:
    _, problems = validate_package(with_sha256(shorts_body(metric)), NOW)
    assert {
        "path": "stop_rules.0.metric",
        "message": "no corresponde al formato shorts",
    } in problems


def test_shorts_defaults_carry_no_invented_retention_threshold() -> None:
    metrics = {rule["metric"] for rule in default_stop_rules("shorts")}
    assert metrics == {"pipeline_e2e", "revenue_vs_cost"}
    assert {"avd_pct", "browse_share_pct"} <= {r["metric"] for r in default_stop_rules("long")}


def test_a_shorts_metric_is_left_to_the_human_until_the_v2_report_is_ingested() -> None:
    rule = shorts_body("engaged_view_ratio_pct")["stop_rules"][0]
    videos = [vid(n) for n in range(1, 12)]
    result = evaluate(
        [rule],
        videos,
        now=NOW,
        authorized_at=NOW.replace(year=NOW.year - 1),
        max_videos=20,
        close_after=2,
    )
    assert result["rules"][0]["status"] == NOT_EVALUABLE
