"""Pure estimation rules for one channel inside a hypothesis. No network, no database."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

LONG_MIN_SECONDS = 180
WINDOW_DAYS = 90
SPIKE_WINDOW_DAYS = 28
MIN_CHANNEL_AGE_DAYS = 180
SMALL_CHANNEL_SUBSCRIBERS = 100_000
TRACTION_RATIO = Decimal("5")
SPIKE_FACTOR = Decimal("2")
SUBSCRIBER_FLOOR = 1_000
_CENTS = Decimal("0.01")
_SHARE = Decimal("0.0001")


@dataclass(frozen=True)
class VideoPoint:
    video_id: str
    published_at: datetime | None
    duration_seconds: float | None
    views: int | None
    language: str | None = None


def is_long(video: VideoPoint) -> bool:
    return video.duration_seconds is not None and video.duration_seconds > LONG_MIN_SECONDS


def _in_window(video: VideoPoint, now: datetime, days: int) -> bool:
    return (
        video.published_at is not None and now - timedelta(days=days) <= video.published_at <= now
    )


def long_views(videos: Sequence[VideoPoint], now: datetime, days: int) -> int:
    return sum(v.views or 0 for v in videos if is_long(v) and _in_window(v, now, days))


def shorts_share(videos: Sequence[VideoPoint], now: datetime, days: int) -> Decimal | None:
    known = [v for v in videos if v.duration_seconds is not None and _in_window(v, now, days)]
    total = sum(v.views or 0 for v in known)
    if total == 0:
        return None
    short = sum(v.views or 0 for v in known if not is_long(v))
    return (Decimal(short) / Decimal(total)).quantize(_SHARE, rounding=ROUND_HALF_UP)


def monthly_long_views(videos: Sequence[VideoPoint], now: datetime) -> int:
    return long_views(videos, now, WINDOW_DAYS) // 3


def income_range(
    monthly_views: int, rpm_low: Decimal, rpm_high: Decimal
) -> tuple[Decimal, Decimal]:
    thousands = Decimal(monthly_views) / Decimal(1000)
    return (
        (thousands * rpm_low).quantize(_CENTS, rounding=ROUND_HALF_UP),
        (thousands * rpm_high).quantize(_CENTS, rounding=ROUND_HALF_UP),
    )


def channel_flags(
    channel_created_at: datetime | None, videos: Sequence[VideoPoint], now: datetime
) -> tuple[str, ...]:
    flags: list[str] = []
    if channel_created_at is not None and now - channel_created_at < timedelta(
        days=MIN_CHANNEL_AGE_DAYS
    ):
        flags.append("young")
    pace_90 = Decimal(long_views(videos, now, WINDOW_DAYS)) / Decimal(WINDOW_DAYS)
    pace_28 = Decimal(long_views(videos, now, SPIKE_WINDOW_DAYS)) / Decimal(SPIKE_WINDOW_DAYS)
    if pace_90 > 0 and pace_28 > SPIKE_FACTOR * pace_90:
        flags.append("spike")
    return tuple(flags)


def max_outlier_ratio(
    videos: Sequence[VideoPoint], subscribers: int | None, now: datetime
) -> Decimal | None:
    window = [v for v in videos if is_long(v) and _in_window(v, now, WINDOW_DAYS)]
    if not window:
        return None
    base = Decimal(max(subscribers or 0, SUBSCRIBER_FLOOR))
    best = max(Decimal(v.views or 0) for v in window)
    return (best / base).quantize(_CENTS, rounding=ROUND_HALF_UP)


def is_traction_channel(subscribers: int | None, ratio: Decimal | None) -> bool:
    return (
        subscribers is not None
        and subscribers < SMALL_CHANNEL_SUBSCRIBERS
        and ratio is not None
        and ratio >= TRACTION_RATIO
    )


def language_ok(videos: Sequence[VideoPoint], wanted: str = "en") -> bool:
    declared = [v.language[:2].lower() for v in videos if v.language]
    if not declared:
        return True
    return declared.count(wanted) / len(declared) >= 0.5
