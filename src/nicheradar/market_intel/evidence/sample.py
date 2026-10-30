"""RPM sample decision (contract §6.4 R2 and D10) using YouTube API data **at read time**.

`listing_evidence.derived` is kept free of API data (it outlives the 30-day API retention), so the
rules that need it cannot be applied when the extraction is saved. They are applied here, to the
fresh snapshot, whenever a sample is read; only the resulting aggregate (RPM) may outlive those
30 days.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from nicheradar.market_intel.evidence.derive import TIER1

SHORTS_MAX_SECONDS = 180  # same threshold as `RecentVideo.is_short`
SHORTS_HEAVY = 0.10
# D10: the sample must describe channels that really monetize in a paying market.
MIN_CHANNEL_AGE_DAYS = 180
MIN_MONETIZED_DAYS = 90
MIN_MONTHLY_INCOME_USD = Decimal(10)
MIN_TIER1_SHARE = 0.30


@dataclass(frozen=True)
class SampleContext:
    """What the API snapshot and the stored extraction say about the listing (None = unknown)."""

    shorts_share: float | None
    channel_age_days: int | None
    country: str | None
    monetized_days: int | None
    tier1_share: float | None


def shorts_share_of_views(videos: Sequence[Mapping[str, Any]]) -> float | None:
    """Share of the recent videos' views that belong to Shorts; None when there are no views."""
    total = sum(int(video["views"]) for video in videos)
    if total <= 0:
        return None
    shorts = sum(
        int(video["views"])
        for video in videos
        if int(video["duration_seconds"]) <= SHORTS_MAX_SECONDS
    )
    return shorts / total


def _market_reason(context: SampleContext) -> str | None:
    if context.tier1_share is not None:
        return None if context.tier1_share >= MIN_TIER1_SHARE else "market_not_tier1"
    if context.country is not None and context.country not in TIER1:
        return "market_not_tier1"
    return None


def sample_decision(derived: Mapping[str, Any], context: SampleContext) -> str:
    """`ok`, or the first reason the listing stays out of the long-form RPM sample.

    An unknown fact (age, monetization date, audience) is never a reason by itself: the rules only
    exclude what the evidence shows.
    """
    primary = derived.get("primary")
    if not derived.get("rpm_sample_eligible") or not primary:
        return "not_eligible"
    scope = primary["scope"]
    if scope == "shorts":
        return "scope_shorts"
    if scope == "all":
        if context.shorts_share is None:
            return "shorts_unknown"
        if context.shorts_share >= SHORTS_HEAVY:
            return "shorts_heavy"
    if context.channel_age_days is not None and context.channel_age_days < MIN_CHANNEL_AGE_DAYS:
        return "channel_too_new"
    if context.monetized_days is not None and context.monetized_days < MIN_MONETIZED_DAYS:
        return "recently_monetized"
    monthly = derived.get("observed_monthly_income_usd")
    if monthly is None or Decimal(str(monthly)) < MIN_MONTHLY_INCOME_USD:
        return "low_income"
    return _market_reason(context) or "ok"
