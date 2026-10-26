# tests/test_pilot_shorts_rules.py
"""Reglas de parada por formato: Shorts usa sus métricas (bench de Shorts), no las del largo."""

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from nicheradar.pilots.contracts import validate_package, with_sha256
from nicheradar.pilots.rules import FAILED, MET, MIN_SHORTS_VIEWS, UNDECIDED, evaluate
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


def svid(n: int, ratio: str | None = "60", views: int = 500, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "video_id": f"s{n:02d}",
        "stage": "measuring" if ratio is not None else "published",
        "published_at": NOW - timedelta(days=60 - n),
        "cost_usd": Decimal("0.10"),
        "cost_equivalent_usd": Decimal("0.40"),
        "machine_minutes": 20,
        "avd_pct": None,
        "browse_share_pct": None,
        "engaged_view_ratio_pct": Decimal(ratio) if ratio is not None else None,
        "avg_view_pct": Decimal("70") if ratio is not None else None,
        "shorts_feed_share_pct": Decimal("85") if ratio is not None else None,
        "views": views if ratio is not None else None,
        "measured_at": NOW - timedelta(days=1) if ratio is not None else None,
    }
    base.update(over)
    return base


def run(videos: list[dict[str, Any]], metric: str = "engaged_view_ratio_pct") -> dict[str, Any]:
    return evaluate(
        [shorts_body(metric)["stop_rules"][0]],
        videos,
        now=NOW,
        authorized_at=NOW - timedelta(days=365),
        max_videos=20,
        close_after=2,
    )


def status(videos: list[dict[str, Any]], metric: str = "engaged_view_ratio_pct") -> str:
    return str(run(videos, metric)["rules"][0]["status"])


def test_the_minimum_views_to_count_is_a_named_constant() -> None:
    assert MIN_SHORTS_VIEWS == 100


@pytest.mark.parametrize("metric", ["engaged_view_ratio_pct", "avg_view_pct"])
def test_a_shorts_count_rule_is_met_when_enough_videos_reach_the_threshold(metric: str) -> None:
    field: dict[str, Any] = {metric: Decimal("60")}
    videos = [svid(n, **field) for n in range(1, 11)]
    assert status(videos, metric) == MET


def test_a_shorts_count_rule_fails_when_it_can_no_longer_be_reached() -> None:
    videos = [svid(n, ratio="10") for n in range(1, 11)]
    assert status(videos) == FAILED


def test_a_video_under_the_minimum_views_is_saved_but_does_not_count() -> None:
    thin = [svid(n, ratio="90", views=MIN_SHORTS_VIEWS - 1) for n in range(1, 4)]
    low = [svid(n, ratio="10") for n in range(4, 11)]
    result = run(thin + low)
    assert result["rules"][0]["status"] == UNDECIDED  # 0 llegan; los 3 delgados siguen sin contar
    enough = [svid(n, ratio="90", views=MIN_SHORTS_VIEWS) for n in range(1, 4)]
    assert status(enough + low) == MET


def test_unmeasured_shorts_keep_the_rule_undecided() -> None:
    videos = [svid(n, ratio="60") for n in range(1, 3)] + [
        svid(n, ratio=None) for n in range(3, 11)
    ]
    assert status(videos) == UNDECIDED


def test_the_feed_share_rule_uses_the_latest_counted_measurement() -> None:
    videos = [svid(n) for n in range(1, 11)]
    assert status(videos, "shorts_feed_share_pct") == MET
    videos[-1]["shorts_feed_share_pct"] = Decimal("10")
    assert status(videos, "shorts_feed_share_pct") == FAILED


def test_shorts_videos_count_as_measured_in_the_totals() -> None:
    videos = [svid(n) for n in range(1, 6)] + [svid(n, ratio=None) for n in range(6, 8)]
    assert run(videos)["totals"]["measured"] == 5


def test_long_form_metrics_still_evaluate_as_before_with_shorts_fields_absent() -> None:
    rule = package_body()["stop_rules"][0]
    videos = [vid(n, avd="25") for n in range(1, 11)]
    result = evaluate(
        [rule],
        videos,
        now=NOW,
        authorized_at=NOW - timedelta(days=365),
        max_videos=20,
        close_after=2,
    )
    assert result["rules"][0]["status"] == MET
