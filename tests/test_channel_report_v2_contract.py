# tests/test_channel_report_v2_contract.py
"""channel-report-v2 (Shorts): forma, coherencia y despacho por `contract`."""

from typing import Any

import pytest

from nicheradar.pilots.contracts import Problem, Report, ReportV2, validate_report
from tests.shorts_report_samples import shorts_measurement, shorts_report, shorts_video
from tests.test_persistence import NOW
from tests.test_pilots_api import report as long_report
from tests.test_pilots_api import video as long_video


def problems_of(body: Any) -> list[Problem]:
    parsed, problems = validate_report(body, NOW)
    assert parsed is None
    return problems


def paths(body: Any) -> set[str]:
    return {problem["path"] for problem in problems_of(body)}


def with_measurement(**over: Any) -> dict[str, Any]:
    return shorts_report([shorts_video(1, measurement=shorts_measurement(**over))])


def test_a_valid_shorts_report_is_accepted_and_dispatched_by_contract() -> None:
    parsed, problems = validate_report(shorts_report(), NOW)
    assert problems == [] and isinstance(parsed, ReportV2)
    parsed_long, problems_long = validate_report(
        long_report("pil_20261101_x", [long_video(1)]), NOW
    )
    assert problems_long == [] and isinstance(parsed_long, Report)


def test_an_unknown_contract_is_rejected_without_echoing_it() -> None:
    problems = problems_of(shorts_report() | {"contract": "channel-report-v9"})
    assert problems and "v9" not in str(problems)


def test_the_format_must_be_shorts() -> None:
    assert "format" in paths(shorts_report(format="long"))
    body = shorts_report()
    del body["format"]
    assert "format" in paths(body)


def test_the_long_form_measurement_is_not_valid_in_v2() -> None:
    body = shorts_report([shorts_video(1, measurement=long_video(1)["measurement"])])
    assert any(p.startswith("videos.0.measurement") for p in paths(body))


def test_the_v2_measurement_is_not_valid_in_v1() -> None:
    body = long_report("pil_20261101_x", [long_video(1, measurement=shorts_measurement())])
    assert any(p.startswith("videos.0.measurement") for p in paths(body))


def test_unknown_keys_are_rejected_without_echoing_them() -> None:
    problems = problems_of(with_measurement(secreto_x=1))
    assert "secreto_x" not in str(problems)
    assert problems[0]["path"] == "videos.0.measurement.(campo no permitido)"


def test_engaged_views_cannot_exceed_views() -> None:
    assert "videos.0.measurement.engaged_views" in paths(with_measurement(engaged_views=2500))


def test_the_ratio_must_match_engaged_views_over_views() -> None:
    assert "videos.0.measurement.engaged_view_ratio_pct" in paths(
        with_measurement(engaged_view_ratio_pct=80)
    )
    near = with_measurement(engaged_view_ratio_pct=65.05)  # dentro de la tolerancia de 0,1
    assert validate_report(near, NOW)[1] == []


def test_the_ratio_is_required_with_views_and_null_without_them() -> None:
    assert "videos.0.measurement.engaged_view_ratio_pct" in paths(
        with_measurement(engaged_view_ratio_pct=None)
    )
    nothing = with_measurement(views=0, engaged_views=0, engaged_view_ratio_pct=None)
    assert validate_report(nothing, NOW)[1] == []
    inconsistent = with_measurement(views=0, engaged_views=0, engaged_view_ratio_pct=50)
    assert "videos.0.measurement.engaged_view_ratio_pct" in paths(inconsistent)


def test_the_early_retention_second_goes_with_its_percentage() -> None:
    assert "videos.0.measurement.early_retention_second" in paths(
        with_measurement(early_retention_pct=80)
    )
    assert "videos.0.measurement.early_retention_second" in paths(
        with_measurement(early_retention_second=3)
    )
    both = with_measurement(early_retention_pct=80, early_retention_second=3)
    assert validate_report(both, NOW)[1] == []


@pytest.mark.parametrize(
    "field", ["avg_view_pct", "shorts_feed_share_pct", "stayed_to_watch_pct", "early_retention_pct"]
)
def test_percentages_stay_between_zero_and_one_hundred(field: str) -> None:
    extra = {"early_retention_second": 3} if field == "early_retention_pct" else {}
    assert f"videos.0.measurement.{field}" in paths(with_measurement(**{field: 100.5}, **extra))


def test_the_v1_coherence_rules_still_apply() -> None:
    no_date = shorts_video(1, published_at=None)
    assert "videos.0.measurement" in paths(shorts_report([no_date]))
    late = with_measurement(measured_at="2020-01-01T00:00:00Z")
    assert "videos.0.measurement.measured_at" in paths(late)
    assert "videos" in paths(shorts_report([shorts_video(1), shorts_video(1)]))
    failed = shorts_video(1, source_state="KILL", measurement=None)
    assert "videos.0.failure_code" in paths(shorts_report([failed]))
