"""Muestra de RPM: los datos de la API se aplican al leer, no se guardan en `derived`."""

from typing import Any

import pytest

from nicheradar.market_intel.evidence.sample import (
    SampleContext,
    sample_decision,
    shorts_share_of_views,
)


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


def derived(scope: str = "long", *, eligible: bool = True, monthly: str | None = "100.00") -> dict:
    return {
        "rpm_sample_eligible": eligible,
        "primary": {"scope": scope},
        "observed_monthly_income_usd": monthly,
    }


def context(**changes: Any) -> SampleContext:
    base: dict[str, Any] = {
        "shorts_share": 0.0,
        "channel_age_days": 400,
        "country": "US",
        "monetized_days": 365,
        "tier1_share": None,
    }
    return SampleContext(**(base | changes))


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
    assert sample_decision(derived(scope), context(shorts_share=share)) == expected


def test_a_set_that_failed_the_other_rules_stays_out_whatever_the_context() -> None:
    assert sample_decision(derived(eligible=False), context()) == "not_eligible"


def test_a_missing_primary_is_not_eligible() -> None:
    bare = {"rpm_sample_eligible": True, "primary": None}
    assert sample_decision(bare, context()) == "not_eligible"


# --- calidad: canales que de verdad monetizan en un mercado de pago (D10) -------------------------


@pytest.mark.parametrize(("age", "expected"), [(179, "channel_too_new"), (180, "ok"), (None, "ok")])
def test_a_channel_younger_than_180_days_is_out_and_an_unknown_age_is_not_a_reason(
    age: int | None, expected: str
) -> None:
    assert sample_decision(derived(), context(channel_age_days=age)) == expected


@pytest.mark.parametrize(
    ("days", "expected"), [(89, "recently_monetized"), (90, "ok"), (None, "ok")]
)
def test_a_channel_monetized_less_than_90_days_is_out_and_an_unknown_date_is_not_a_reason(
    days: int | None, expected: str
) -> None:
    assert sample_decision(derived(), context(monetized_days=days)) == expected


@pytest.mark.parametrize(
    ("monthly", "expected"),
    [("9.99", "low_income"), ("10.00", "ok"), ("0.001", "low_income"), (None, "low_income")],
)
def test_a_channel_earning_less_than_ten_dollars_a_month_is_out(
    monthly: str | None, expected: str
) -> None:
    assert sample_decision(derived(monthly=monthly), context()) == expected


@pytest.mark.parametrize(
    ("country", "tier1", "expected"),
    [
        ("ID", None, "market_not_tier1"),
        ("KH", None, "market_not_tier1"),
        ("US", None, "ok"),
        (None, None, "ok"),
        ("ID", 0.45, "ok"),
        ("US", 0.10, "market_not_tier1"),
        (None, 0.29, "market_not_tier1"),
        (None, 0.30, "ok"),
    ],
)
def test_the_market_comes_from_the_audience_when_known_and_from_the_country_otherwise(
    country: str | None, tier1: float | None, expected: str
) -> None:
    assert sample_decision(derived(), context(country=country, tier1_share=tier1)) == expected


def test_the_first_failing_rule_is_the_one_reported() -> None:
    assert (
        sample_decision(derived("shorts", monthly="1"), context(channel_age_days=10, country="ID"))
        == "scope_shorts"
    )
