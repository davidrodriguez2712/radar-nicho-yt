"""RPM sample decision (contract §6.4, R2) using YouTube API data **at read time**.

`listing_evidence.derived` is kept free of API data (it outlives the 30-day API retention), so the
Shorts rule cannot be applied when the extraction is saved. It is applied here, to the fresh
snapshot, whenever a sample is read; only the resulting aggregate (RPM) may outlive those 30 days.
"""

from collections.abc import Mapping, Sequence
from typing import Any

SHORTS_MAX_SECONDS = 180  # same threshold as `RecentVideo.is_short`
SHORTS_HEAVY = 0.10


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


def sample_decision(derived: Mapping[str, Any], shorts_share: float | None) -> str:
    """`ok`, or the reason the listing stays out of the long-form RPM sample."""
    primary = derived.get("primary")
    if not derived.get("rpm_sample_eligible") or not primary:
        return "not_eligible"
    scope = primary["scope"]
    if scope == "shorts":
        return "scope_shorts"
    if scope == "long":
        return "ok"
    if shorts_share is None:
        return "shorts_unknown"
    return "shorts_heavy" if shorts_share >= SHORTS_HEAVY else "ok"
