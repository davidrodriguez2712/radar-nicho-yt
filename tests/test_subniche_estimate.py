# tests/test_subniche_estimate.py
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from nicheradar.subniche_discovery.estimate import (
    VideoPoint,
    channel_flags,
    income_range,
    is_traction_channel,
    language_ok,
    long_views,
    max_outlier_ratio,
    monthly_long_views,
    shorts_share,
)

NOW = datetime(2026, 10, 31, 12, tzinfo=UTC)


def video(
    days_ago: int, views: int, duration: float = 600, language: str | None = None
) -> VideoPoint:
    return VideoPoint(
        f"v{days_ago}-{views}", NOW - timedelta(days=days_ago), duration, views, language
    )


def test_long_views_counts_only_long_videos_inside_the_window() -> None:
    videos = [video(10, 1000), video(10, 500, duration=60), video(120, 9000)]
    assert long_views(videos, NOW, 90) == 1000


def test_videos_without_date_or_duration_are_ignored() -> None:
    videos = [VideoPoint("a", None, 600, 100), VideoPoint("b", NOW, None, 100)]
    assert long_views(videos, NOW, 90) == 0


def test_monthly_long_views_is_the_90_day_pace() -> None:
    assert monthly_long_views([video(10, 3000), video(60, 3000)], NOW) == 2000


def test_income_range_applies_rpm_per_thousand_views() -> None:
    assert income_range(100_000, Decimal("3.5"), Decimal("8")) == (
        Decimal("350.00"),
        Decimal("800.00"),
    )


def test_shorts_share_is_none_without_views_and_a_fraction_otherwise() -> None:
    assert shorts_share([], NOW, 90) is None
    videos = [video(5, 750), video(5, 250, duration=45)]
    assert shorts_share(videos, NOW, 90) == Decimal("0.2500")


def test_young_channel_is_flagged() -> None:
    assert "young" in channel_flags(NOW - timedelta(days=21), [video(5, 100)], NOW)
    assert "young" not in channel_flags(NOW - timedelta(days=400), [video(5, 100)], NOW)


def test_unknown_channel_age_is_not_flagged_young() -> None:
    assert "young" not in channel_flags(None, [video(5, 100)], NOW)


def test_a_burst_in_the_last_28_days_is_a_spike() -> None:
    assert "spike" in channel_flags(NOW - timedelta(days=900), [video(5, 10_000)], NOW)


def test_steady_output_is_not_a_spike() -> None:
    weekly = [video(day, 1000) for day in range(3, 90, 7)]
    assert "spike" not in channel_flags(NOW - timedelta(days=900), weekly, NOW)


def test_outlier_ratio_uses_the_subscriber_floor() -> None:
    assert max_outlier_ratio([video(5, 50_000)], 200, NOW) == Decimal("50.00")
    assert max_outlier_ratio([video(5, 50_000)], 100_000, NOW) == Decimal("0.50")


def test_hidden_subscribers_use_the_floor_and_never_divide_by_zero() -> None:
    assert max_outlier_ratio([video(5, 4000)], None, NOW) == Decimal("4.00")
    assert max_outlier_ratio([video(5, 4000)], 0, NOW) == Decimal("4.00")
    assert max_outlier_ratio([], 500, NOW) is None


def test_traction_needs_a_small_channel_and_ratio_of_five() -> None:
    assert is_traction_channel(5_000, Decimal("5")) is True
    assert is_traction_channel(5_000, Decimal("4.99")) is False
    assert is_traction_channel(150_000, Decimal("40")) is False
    assert is_traction_channel(None, Decimal("40")) is False
    assert is_traction_channel(5_000, None) is False


def test_language_ok_defaults_to_true_when_nothing_is_declared() -> None:
    assert language_ok([video(5, 1)]) is True
    assert language_ok([video(5, 1, language="fr"), video(6, 1, language="fr-CA")]) is False
    assert language_ok([video(5, 1, language="en-US"), video(6, 1, language="fr")]) is True
