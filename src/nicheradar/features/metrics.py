from collections import Counter, defaultdict
from datetime import datetime
from statistics import median

from pydantic import Field

from nicheradar.discovery.sampling import Membership
from nicheradar.integrations.contracts import Contract


class CohortMetrics(Contract):
    method_version: str = "cohort-metrics-v2"
    videos: int
    channels: int
    demand_by_age: dict[str, float | None]
    supply: dict[str, int]
    active_channels: dict[str, int]
    views_subscriber_ratios: dict[str, float | None]
    breakout_rate: float | None
    breakout_classified: int
    breakout_eligible: int
    breakout_channels: int
    breakout_coverage: float | None
    hhi: float | None
    concentration_score: float | None
    top5_share: float | None
    excluded: dict[str, int]
    limitations: tuple[str, ...] = ()
    trend_relative_change: float | None = None
    best_channel_views_per_day: float | None = None
    worst_channel_views_per_day: float | None = None


class ViewSnapshot(Contract):
    observed_at: datetime
    views: dict[str, int] = Field(default_factory=dict)


def observed_trend(snapshots: tuple[ViewSnapshot, ...]) -> float | None:
    if len(snapshots) != 3:
        return None
    first, middle, last = sorted(snapshots, key=lambda snapshot: snapshot.observed_at)
    keys = set(first.views)
    if not keys or keys != set(middle.views) or keys != set(last.views):
        return None
    seconds_a = (middle.observed_at - first.observed_at).total_seconds()
    seconds_b = (last.observed_at - middle.observed_at).total_seconds()
    if seconds_a <= 0 or seconds_a != seconds_b:
        return None
    if any(
        middle.views[key] < first.views[key] or last.views[key] < middle.views[key] for key in keys
    ):
        return None
    before = sum(middle.views[key] - first.views[key] for key in keys) / seconds_a
    after = sum(last.views[key] - middle.views[key] for key in keys) / seconds_b
    return (after - before) / before if before > 0 else None


def calculate(
    members: tuple[Membership, ...],
    now: datetime,
    *,
    baseline_minimum: int = 5,
    breakout_threshold: float = 5,
) -> CohortMetrics:
    valid = [member for member in members if member.included]
    formats = {member.video.format for member in valid}
    if len(formats) > 1:
        raise ValueError("mixed formats cannot be evaluated as one cohort")
    rates: dict[str, list[float]] = defaultdict(list)
    channel_rates: dict[str, list[float]] = defaultdict(list)
    views_by_channel: dict[str, int] = defaultdict(int)
    for member in valid:
        video = member.video
        if video.views is not None:
            views_by_channel[video.channel_id] += video.views
            if video.published_at:
                days = (now - video.published_at).total_seconds() / 86400
                if days > 0:
                    rates[member.age_band].append(video.views / days)
                    channel_rates[video.channel_id].append(video.views / days)
    channel_medians = [median(values) for values in channel_rates.values()]
    total = sum(views_by_channel.values())
    n = len(views_by_channel)
    shares = [views / total for views in views_by_channel.values()] if total > 0 else []
    hhi = sum(share * share for share in shares) if shares and n >= 2 else None
    concentration = 100 * (1 - (hhi - 1 / n) / (1 - 1 / n)) if hhi is not None and n > 1 else None
    small = [member for member in valid if member.size_stratum == "small"]
    classified, breakout, classified_channels = 0, 0, set()
    only_outliers = bool(valid) and all(
        member.selection_method in {"outliers", "popular"} for member in valid
    )
    if not only_outliers:
        for member in small:
            if member.selection_method in {"outliers", "popular"} or member.video.views is None:
                continue
            baseline = [
                other.video.views
                for other in valid
                if other.video.id != member.video.id
                and other.video.channel_id == member.video.channel_id
                and other.age_band == member.age_band
                and other.video.views is not None
                and other.selection_method not in {"outliers", "popular"}
            ]
            if len(baseline) < baseline_minimum:
                continue
            typical = median(baseline)
            if typical <= 0:
                continue
            classified += 1
            classified_channels.add(member.video.channel_id)
            breakout += member.video.views >= breakout_threshold * typical
    eligible = len(
        [member for member in small if member.selection_method not in {"outliers", "popular"}]
    )
    supply, active = {}, {}
    for window in (7, 30, 90):
        recent = [
            member
            for member in valid
            if member.video.published_at
            and 0 <= (now - member.video.published_at).total_seconds() <= window * 86400
        ]
        supply[str(window)] = len(recent)
        active[str(window)] = len({member.video.channel_id for member in recent})
    return CohortMetrics(
        videos=sum(member.video.views is not None for member in valid),
        channels=len(views_by_channel),
        demand_by_age={band: median(values) for band, values in rates.items()},
        supply=supply,
        active_channels=active,
        views_subscriber_ratios={
            member.video.id: member.video.views / member.video.subscriber_count
            if member.video.views is not None
            and member.video.subscriber_count is not None
            and member.video.subscriber_count > 0
            else None
            for member in valid
        },
        breakout_rate=breakout / classified if classified else None,
        breakout_classified=classified,
        breakout_eligible=eligible,
        breakout_channels=len(classified_channels),
        breakout_coverage=classified / eligible if eligible else None,
        hhi=hhi,
        concentration_score=concentration,
        top5_share=sum(sorted(shares, reverse=True)[:5]) if shares and n >= 2 else None,
        excluded=dict(Counter(member.reason for member in members if not member.included)),
        limitations=(
            "Observed sample, not niche population.",
            "Views/day is average since publication, not observed recent velocity.",
            "Subscriber counts are current observations, not publication-time size.",
        )
        + (("Only selected successes; breakout rate unavailable.",) if only_outliers else ()),
        best_channel_views_per_day=max(channel_medians) if channel_medians else None,
        worst_channel_views_per_day=min(channel_medians) if channel_medians else None,
    )
