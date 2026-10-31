# src/nicheradar/subniche_discovery/aggregate.py
"""Per-hypothesis profile from the channel hits. Pure; every income stays an estimate range."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from statistics import median
from typing import Any

from nicheradar.subniche_discovery.estimate import SMALL_CHANNEL_SUBSCRIBERS

VOLATILE_FLAGS = frozenset({"young", "spike"})
_CENTS = Decimal("0.01")


@dataclass(frozen=True)
class HitMetrics:
    channel_id: str
    source: str
    rank: int | None
    subscribers: int | None
    monthly_long_views: int
    income_low: Decimal | None
    income_high: Decimal | None
    shorts_share: Decimal | None
    outlier_ratio_max: Decimal | None
    small_channel: bool
    traction: bool
    flags: tuple[str, ...]
    excluded_reason: str | None


def is_stable(hit: HitMetrics) -> bool:
    return hit.excluded_reason is None and not VOLATILE_FLAGS & set(hit.flags)


def _median(values: list[Decimal]) -> str | None:
    if not values:
        return None
    return str(Decimal(median(values)).quantize(_CENTS, rounding=ROUND_HALF_UP))


def build_profile(hits: Sequence[HitMetrics], *, rpm_source: str | None) -> dict[str, Any]:
    included = [hit for hit in hits if hit.excluded_reason is None]
    stable = [hit for hit in included if is_stable(hit)]
    traction = [hit for hit in included if hit.traction]
    return {
        "channels_seen": len(hits),
        "channels_included": len(included),
        "stable_channels": len(stable),
        "volatile_channels": len(included) - len(stable),
        "excluded": dict(Counter(hit.excluded_reason for hit in hits if hit.excluded_reason)),
        "traction_channels": len(traction),
        "median_outlier_ratio": _median(
            [hit.outlier_ratio_max for hit in traction if hit.outlier_ratio_max is not None]
        ),
        "large_channels": sum(
            1
            for hit in included
            if hit.subscribers is not None and hit.subscribers >= SMALL_CHANNEL_SUBSCRIBERS
        ),
        "median_income_low": _median([h.income_low for h in stable if h.income_low is not None]),
        "median_income_high": _median([h.income_high for h in stable if h.income_high is not None]),
        "rpm_source": rpm_source,
        "estimate": True,
        "signal": "estimable" if included else "sin_senal",
    }
