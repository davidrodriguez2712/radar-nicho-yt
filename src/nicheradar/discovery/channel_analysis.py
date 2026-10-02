"""Bounded, on-demand channel competitive analysis: resolve a channel, pull its real
videos, discover real comparables, and compute the same metrics/profit machinery already
used for catalog opportunities -- scoped to a single owner-requested channel, not the
seed-family catalog.
"""

import re
from datetime import datetime
from statistics import median

from nicheradar.integrations.contracts import Channel, Operation, ProviderError, Video
from nicheradar.services.gateway import Gateway

_HANDLE = re.compile(r"@([A-Za-z0-9_.-]+)")
_CHANNEL_ID = re.compile(r"(UC[A-Za-z0-9_-]{22})")


def parse_channel_input(raw: str) -> dict[str, str]:
    raw = raw.strip()
    channel_id_match = _CHANNEL_ID.search(raw)
    if channel_id_match and "/@" not in raw:
        return {"id": channel_id_match.group(1)}
    handle_match = _HANDLE.search(raw)
    if handle_match:
        return {"forHandle": handle_match.group(1)}
    raise ValueError("unsupported_channel_input")


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
}


async def discover_comparables(
    youtube_gateway: Gateway,
    vidiq_gateway: Gateway | None,
    target: Channel,
    now: datetime,
    *,
    max_comparables: int = MAX_COMPARABLES,
) -> tuple[Channel, ...]:
    query = target.category or (target.subtopics[0] if target.subtopics else target.title)
    found: dict[str, Channel] = {}

    youtube_batch, _, _ = await youtube_gateway.fetch(
        Operation.SEARCH, {"type": "channel", "q": query, "maxResults": "25"}, now
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

    found.pop(target.id, None)
    return tuple(found.values())[:max_comparables]
