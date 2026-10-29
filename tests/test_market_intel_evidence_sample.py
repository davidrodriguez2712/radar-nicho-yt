"""Muestra de RPM: los datos de la API (Shorts) se aplican al leer, no se guardan en `derived`."""

from typing import Any

import pytest

from nicheradar.market_intel.evidence.sample import sample_decision, shorts_share_of_views


def video(views: int, seconds: int) -> dict[str, Any]:
    return {"views": views, "duration_seconds": seconds}


def test_shorts_share_is_the_share_of_views_of_videos_up_to_three_minutes() -> None:
    videos = [video(900, 600), video(100, 59), video(100, 180), video(0, 20)]
    assert shorts_share_of_views(videos) == pytest.approx(200 / 1100)


@pytest.mark.parametrize("videos", [[], [video(0, 30)], [video(0, 600)]])
def test_shorts_share_is_unknown_without_views(videos: list[dict[str, Any]]) -> None:
    assert shorts_share_of_views(videos) is None


def test_a_video_of_181_seconds_is_not_a_short() -> None:
    assert shorts_share_of_views([video(100, 181)]) == 0.0


def derived(scope: str, *, eligible: bool = True) -> dict[str, Any]:
    return {"rpm_sample_eligible": eligible, "primary": {"scope": scope}}


@pytest.mark.parametrize(
    ("scope", "share", "expected"),
    [
        ("long", None, "ok"),
        ("long", 0.9, "ok"),
        ("all", 0.0, "ok"),
        ("all", 0.0999, "ok"),
        ("all", 0.10, "shorts_heavy"),
        ("all", 0.8, "shorts_heavy"),
        ("all", None, "shorts_unknown"),
        ("shorts", 0.0, "scope_shorts"),
    ],
)
def test_the_shorts_rule_applies_to_the_whole_channel_scope(
    scope: str, share: float | None, expected: str
) -> None:
    assert sample_decision(derived(scope), share) == expected


def test_a_set_that_failed_the_other_rules_stays_out_whatever_the_shorts_share() -> None:
    assert sample_decision(derived("long", eligible=False), 0.0) == "not_eligible"


def test_a_missing_primary_is_not_eligible() -> None:
    assert sample_decision({"rpm_sample_eligible": True, "primary": None}, 0.0) == "not_eligible"
