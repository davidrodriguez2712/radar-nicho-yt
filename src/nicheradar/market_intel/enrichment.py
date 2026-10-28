# src/nicheradar/market_intel/enrichment.py
"""Enrich listings with public YouTube channel data (listing-evidence-v1 `api` block).

Per channel: one batched `channels.list` (50 ids per call), one uploads page and one
`videos.list` for the 10 latest videos. The result is a dated snapshot, never an input to the
niche statistics on its own: it gives channel age, real view totals and the recent upload pattern
that seller-declared numbers cannot. YouTube API data is kept at most 30 days without a refresh.
"""

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import Connection, case, select

from nicheradar.integrations.contracts import Channel, Operation, ProviderError, Video
from nicheradar.market_intel.context import RunContext
from nicheradar.repositories.core import get_profile
from nicheradar.repositories.schema import listing_channel_snapshots as snapshots
from nicheradar.repositories.schema import marketplace_listings as ml
from nicheradar.services.channel_analysis_providers import (
    channel_analysis_youtube_limits,
    channel_analysis_youtube_tariffs,
)
from nicheradar.services.gateway import Gateway
from nicheradar.services.youtube_enrichment import youtube_provider

ENRICH_TTL = timedelta(days=25)  # refreshed before the 30-day retention below runs out
SNAPSHOT_RETENTION = timedelta(days=30)
RECENT_VIDEOS = 10
BATCH_SIZE = 50
# channels (1/50) + uploads + videos per channel, plus headroom for the verify stage's calls.
CALLS_PER_CHANNEL = 2


class Fetcher(Protocol):
    async def channels(self, channel_ids: list[str]) -> dict[str, Channel]: ...

    async def recent_videos(self, channel: Channel) -> tuple[Video, ...]: ...


def pending_enrichment(
    connection: Connection, source: str, limit: int, now: datetime
) -> list[dict[str, Any]]:
    recent = select(snapshots.c.listing_id).where(snapshots.c.fetched_at >= now - ENRICH_TTL)
    income_first = case((ml.c.income_monthly_usd > 0, 0), else_=1)
    rows = connection.execute(
        select(ml.c.id, ml.c.youtube_channel_id)
        .where(
            ml.c.source == source,
            ml.c.status == "active",
            ml.c.youtube_channel_id.is_not(None),
            ml.c.id.not_in(recent),
        )
        .order_by(
            income_first, ml.c.income_monthly_usd.desc().nulls_last(), ml.c.external_id.desc()
        )
        .limit(limit)
    ).mappings()
    return [dict(row) for row in rows]


def save_snapshot(
    connection: Connection,
    listing_id: UUID,
    channel_id: str,
    channel: Channel | None,
    videos: tuple[Video, ...],
    now: datetime,
) -> None:
    ordered = sorted(
        videos,
        key=lambda v: v.published_at or datetime.min.replace(tzinfo=now.tzinfo),
        reverse=True,
    )
    connection.execute(
        snapshots.insert().values(
            id=uuid4(),
            listing_id=listing_id,
            youtube_channel_id=channel_id,
            status="ok" if channel else "not_found",
            fetched_at=now,
            title=channel.title[:200] if channel else None,
            country=channel.country if channel and channel.country else None,
            channel_created_at=channel.published_at if channel else None,
            subscribers=channel.subscribers if channel else None,
            total_views=channel.total_views if channel else None,
            video_count=channel.video_count if channel else None,
            recent_videos=[
                {
                    "video_id": video.id,
                    "title": video.title[:120],
                    "published_at": video.published_at.isoformat() if video.published_at else None,
                    "duration_seconds": int(video.duration_seconds)
                    if video.duration_seconds is not None
                    else None,
                    "views": video.views,
                }
                for video in ordered[:RECENT_VIDEOS]
            ],
            retain_until=now + SNAPSHOT_RETENTION,
        )
    )


class GatewayFetcher:
    def __init__(self, gateway: Gateway, clock: Callable[[], datetime]) -> None:
        self.gateway = gateway
        self.clock = clock

    async def channels(self, channel_ids: list[str]) -> dict[str, Channel]:
        batch, _, _ = await self.gateway.fetch(
            Operation.CHANNELS, {"id": ",".join(channel_ids)}, self.clock()
        )
        return {channel.id: channel for channel in batch.channels}

    async def recent_videos(self, channel: Channel) -> tuple[Video, ...]:
        if not channel.uploads_playlist:
            return ()
        uploads, _, _ = await self.gateway.fetch(
            Operation.UPLOADS,
            {"playlistId": channel.uploads_playlist, "maxResults": str(RECENT_VIDEOS)},
            self.clock(),
        )
        ids = [video.id for video in uploads.videos][:RECENT_VIDEOS]
        if not ids:
            return ()
        batch, _, _ = await self.gateway.fetch(
            Operation.VIDEOS, {"id": ",".join(ids)}, self.clock()
        )
        return batch.videos


def build_fetcher(ctx: RunContext, channels_to_fetch: int) -> Fetcher:
    """Raises ProviderError when YouTube is not configured; the Gateway enforces quota/policy."""
    config = ctx.config
    youtube = youtube_provider(config)
    with ctx.engine.connect() as connection:
        profile_id, _, profile = get_profile(connection)
    batches = -(-channels_to_fetch // BATCH_SIZE)
    gateway = Gateway(
        ctx.engine,
        youtube,
        profile_id,
        ctx.analysis_run["id"],
        str(config.youtube_auth_scope),
        profile,
        channel_analysis_youtube_limits(config),
        channel_analysis_youtube_tariffs(),
        # The Gateway counts every YouTube request of this analysis run, verification included.
        maximum_calls=config.market_intel_verify_cap_per_run
        + batches
        + CALLS_PER_CHANNEL * channels_to_fetch
        + 10,
    )
    return GatewayFetcher(gateway, ctx.clock)


async def _enrich(
    ctx: RunContext, pending: list[dict[str, Any]], fetcher: Fetcher
) -> dict[str, Any]:
    saved = not_found = 0
    stopped: str | None = None
    for start in range(0, len(pending), BATCH_SIZE):
        group = pending[start : start + BATCH_SIZE]
        try:
            found = await fetcher.channels(list({item["youtube_channel_id"] for item in group}))
        except ProviderError as error:
            stopped = error.code
            break
        for item in group:
            channel = found.get(item["youtube_channel_id"])
            videos: tuple[Video, ...] = ()
            if channel is not None:
                try:
                    videos = await fetcher.recent_videos(channel)
                except ProviderError as error:
                    stopped = error.code
                    break
            with ctx.engine.begin() as connection:
                save_snapshot(
                    connection, item["id"], item["youtube_channel_id"], channel, videos, ctx.clock()
                )
            saved += 1
            not_found += channel is None
        if stopped is not None:
            break
    result: dict[str, Any] = {"pending": len(pending), "saved": saved, "not_found": not_found}
    if stopped is not None:
        result |= {"stopped_reason": stopped, "partial": True}
    return result


def stage_enrich(ctx: RunContext, fetcher: Fetcher | None = None) -> dict[str, Any]:
    config = ctx.config
    if ctx.analysis_run["mode"] != "live":
        return {"skipped": "synthetic_mode"}
    cap = config.market_intel_enrich_cap_per_run
    if cap == 0 or not config.youtube_live_enabled:
        return {"skipped": "youtube_not_enabled"}
    with ctx.engine.connect() as connection:
        pending = pending_enrichment(connection, ctx.source.name, cap, ctx.clock())
    if not pending:
        return {"pending": 0, "saved": 0, "not_found": 0}
    try:
        client = fetcher or build_fetcher(ctx, len(pending))
    except ProviderError as error:
        return {"skipped": error.code, "partial": True}
    return asyncio.run(_enrich(ctx, pending, client))
