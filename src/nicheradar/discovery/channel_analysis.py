"""Bounded, on-demand channel competitive analysis: resolve a channel, pull its real
videos, discover real comparables, and compute the same metrics/profit machinery already
used for catalog opportunities -- scoped to a single owner-requested channel, not the
seed-family catalog.
"""

import re
from collections import Counter
from datetime import datetime
from statistics import median
from typing import Any, Literal, NamedTuple

from nicheradar.discovery.sampling import Membership, age_band
from nicheradar.domain.production import EstimateRange
from nicheradar.domain.profile import VideoFormat
from nicheradar.features.metrics import calculate
from nicheradar.integrations.contracts import Channel, Operation, ProviderError, Video
from nicheradar.scoring.advertising import AdvertisingBenchmark
from nicheradar.scoring.profit import estimate_profit
from nicheradar.services.gateway import Gateway

_HANDLE = re.compile(r"@([A-Za-z0-9_.-]+)")
_CHANNEL_ID = re.compile(r"(UC[A-Za-z0-9_-]{22})")
_HASHTAG = re.compile(r"#(\w+)")


def parse_channel_input(raw: str) -> dict[str, str]:
    raw = raw.strip()
    channel_id_match = _CHANNEL_ID.search(raw)
    if channel_id_match and "/@" not in raw:
        return {"id": channel_id_match.group(1)}
    handle_match = _HANDLE.search(raw)
    if handle_match:
        return {"forHandle": handle_match.group(1)}
    raise ValueError("unsupported_channel_input")


def _discovery_query(target: Channel) -> str:
    if target.keywords:
        return target.keywords[0]
    if target.description:
        hashtag = _HASHTAG.search(target.description)
        if hashtag:
            return hashtag.group(1)
    return target.title


async def resolve_channel(gateway: Gateway, raw_input: str, now: datetime) -> Channel:
    params = parse_channel_input(raw_input)
    batch, _, _ = await gateway.fetch(Operation.CHANNELS, params, now)
    if not batch.channels:
        raise ProviderError("channel_not_found", not_sent=True)
    return batch.channels[0]


def channel_view_rate(videos: tuple[Video, ...], now: datetime) -> float | None:
    rates = []
    for video in videos:
        if video.views is None or video.published_at is None:
            continue
        days = (now - video.published_at).total_seconds() / 86400
        if days > 0:
            rates.append(video.views / days)
    return median(rates) if rates else None


async def fetch_channel_videos(
    gateway: Gateway, channel: Channel, now: datetime
) -> tuple[Video, ...]:
    if channel.uploads_playlist:
        uploads, _, _ = await gateway.fetch(
            Operation.UPLOADS, {"playlistId": channel.uploads_playlist, "maxResults": "25"}, now
        )
        video_ids = [video.id for video in uploads.videos][:25]
        if video_ids:
            batch, _, _ = await gateway.fetch(Operation.VIDEOS, {"id": ",".join(video_ids)}, now)
            return batch.videos
    return ()


MAX_COMPARABLES = 8
VIDIQ_BUDGET_ERROR_CODES = {
    "run_budget_exhausted",
    "period_budget_exhausted",
    "balance_exhausted",
    "balance_refresh_required",
    "quota",  # vidIQ maps HTTP 429 (rate limit) to "quota"
}


class ComparableDiscovery(NamedTuple):
    comparables: tuple[Channel, ...]
    # "budget_exhausted" when a planned vidIQ call was skipped for budget reasons;
    # None when vidIQ ran or was never part of this run (synthetic/YouTube-only).
    vidiq_omitted: str | None = None


async def discover_comparables(
    youtube_gateway: Gateway,
    vidiq_gateway: Gateway | None,
    target: Channel,
    now: datetime,
    *,
    max_comparables: int = MAX_COMPARABLES,
) -> ComparableDiscovery:
    query = _discovery_query(target)
    found: dict[str, Channel] = {}
    vidiq_omitted: str | None = None

    youtube_batch, _, _ = await youtube_gateway.fetch(
        Operation.SEARCH, {"type": "channel", "q": query, "maxResults": "50"}, now
    )
    for channel in youtube_batch.channels:
        found[channel.id] = channel

    if vidiq_gateway is not None:
        try:
            vidiq_batch, _, _ = await vidiq_gateway.fetch(
                Operation.CHANNEL_SEARCH, {"query": query}, now
            )
            for channel in vidiq_batch.channels:
                found[channel.id] = channel
        except ProviderError as error:
            if error.code not in VIDIQ_BUDGET_ERROR_CODES:
                raise
            vidiq_omitted = "budget_exhausted"

    found.pop(target.id, None)
    comparables: dict[str, Channel] = dict(list(found.items())[:max_comparables])

    # Neither SEARCH's nor vidIQ's CHANNEL_SEARCH's channel normalization reliably
    # provides both `subscribers` and `uploads_playlist` (SEARCH gives neither; vidIQ
    # gives subscribers but never uploads_playlist) -- without these, Task 10's
    # subscriber-based breakout classification silently has no real data to work with,
    # and fetch_channel_videos cannot fetch ANY videos for the comparable at all. One
    # extra batched channels.list call (<=50 ids, 1 unit total) resolves both for
    # whichever comparables still need it; a comparable that already has both (from a
    # provider that supplies them) is skipped to avoid spending budget on data that's
    # already real.
    missing_ids = [
        channel_id
        for channel_id, channel in comparables.items()
        if channel.subscribers is None or channel.uploads_playlist is None
    ]
    if missing_ids:
        try:
            resolved_batch, _, _ = await youtube_gateway.fetch(
                Operation.CHANNELS, {"id": ",".join(missing_ids)}, now
            )
        except ProviderError:
            # Graceful degrade, not data loss: keep the thin (search-only) comparables
            # already found rather than losing the whole discovery over this bonus call.
            resolved_batch = None
        if resolved_batch is not None:
            for resolved in resolved_batch.channels:
                if resolved.id in comparables:
                    comparables[resolved.id] = resolved

    return ComparableDiscovery(tuple(comparables.values()), vidiq_omitted)


def compute_comparison(
    target_videos: tuple[Video, ...],
    target: Channel,
    comparable_videos: dict[str, tuple[Video, ...]],
    now: datetime,
    *,
    videos_per_month: int | None = None,
    advertising: AdvertisingBenchmark | None = None,
    monthly_cost_usd: EstimateRange | None = None,
) -> dict[str, Any]:
    target_rate = channel_view_rate(target_videos, now)
    rates = [
        rate
        for videos in comparable_videos.values()
        if (rate := channel_view_rate(videos, now)) is not None
    ]
    best = max(rates) if rates else None
    worst = min(rates) if rates else None
    position = "unknown"
    if target_rate is not None and best is not None and worst is not None:
        position = "above" if target_rate > best else "below" if target_rate < worst else "within"
    profit = estimate_profit(
        best_channel_views_per_day=best,
        worst_channel_views_per_day=worst,
        videos_per_month=videos_per_month,
        advertising=advertising,
        monthly_cost_usd=monthly_cost_usd,
    )
    return {
        "target_view_rate": target_rate,
        "comparable_best": best,
        "comparable_worst": worst,
        "target_position": position,
        "profit": profit.model_dump(mode="json"),
    }


def compute_panorama(
    comparable_videos: dict[str, tuple[Video, ...]],
    comparable_channels: tuple[Channel, ...],
    small_channel_subscribers: int,
    now: datetime,
) -> dict[str, Any]:
    subscribers_by_channel = {channel.id: channel.subscribers for channel in comparable_channels}
    # Keyed by `comparable_videos`'s own dict key (the comparable channel actually
    # iterated when these videos were fetched), not `video.channel_id`: verified empirically
    # that `fetch_channel_videos` can return videos whose `channel_id` does not match the
    # requested comparable (confirmed for SyntheticProvider, whose UPLOADS/VIDEOS fixture
    # ignores the requested channel and always reports "channel-0" as the owner) -- using
    # `video.channel_id` here would silently misclassify every comparable's videos under
    # the wrong channel's subscriber count.
    all_videos = [
        (channel_id, video) for channel_id, videos in comparable_videos.items() for video in videos
    ]
    if not all_videos:
        return {"status": "incomplete", "reason": "no_comparable_videos"}
    # A single UNKNOWN-format video (routine with real YouTube data, since
    # YouTubeProvider never sets `format`) must not wipe out the whole cohort's
    # panorama. Evaluate the most common CONFIRMED format only; videos with a
    # different confirmed format or an UNKNOWN format are excluded (included=False,
    # with a reason), not dropped, so `calculate()`'s own accounting (e.g. `excluded`)
    # still sees them -- same convention `discovery/sampling.py::sample()` uses.
    confirmed_formats = [
        video.format for _, video in all_videos if video.format != VideoFormat.UNKNOWN
    ]
    if not confirmed_formats:
        return {"status": "incomplete", "reason": "no_confirmed_format_videos"}
    majority_format = Counter(confirmed_formats).most_common(1)[0][0]

    def stratum(channel_id: str) -> Literal["small", "large", "unknown"]:
        subscribers = subscribers_by_channel.get(channel_id)
        if subscribers is None:
            return "unknown"
        return "small" if subscribers <= small_channel_subscribers else "large"

    def membership_reason(video: Video) -> str:
        if video.format == VideoFormat.UNKNOWN:
            return "format_unknown"
        if video.format != majority_format:
            return "different_format"
        return "channel_analysis_comparable"

    members = tuple(
        Membership(
            video=video,
            included=video.format == majority_format,
            reason=membership_reason(video),
            size_stratum=stratum(channel_id),
            age_band=age_band((now - video.published_at).total_seconds() / 86400)
            if video.published_at
            else "unknown",
            selection_method="channel_analysis",
        )
        for channel_id, video in all_videos
    )
    metrics = calculate(members, now)
    return {"status": "computed", "metrics": metrics.model_dump(mode="json")}
