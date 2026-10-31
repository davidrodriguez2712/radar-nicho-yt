# src/nicheradar/subniche_discovery/measure.py
"""Measure one hypothesis: search -> top channels -> recent videos -> estimates -> one write."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Engine

from nicheradar.config import Settings
from nicheradar.integrations.contracts import Channel, ProviderError, Video
from nicheradar.market_intel.enrichment import BATCH_SIZE, CHANNEL_LEVEL_FAILURES
from nicheradar.subniche_discovery.aggregate import HitMetrics, build_profile
from nicheradar.subniche_discovery.estimate import (
    SMALL_CHANNEL_SUBSCRIBERS,
    WINDOW_DAYS,
    VideoPoint,
    channel_flags,
    income_range,
    is_traction_channel,
    language_ok,
    max_outlier_ratio,
    monthly_long_views,
    shorts_share,
)
from nicheradar.subniche_discovery.persist import rpm_range, save_measurement
from nicheradar.subniche_discovery.reader import YouTubeReader

RECENT_VIDEOS_LIMIT = 30


async def _channels_of(reader: YouTubeReader, ids: list[str]) -> dict[str, Channel]:
    """One batched call; if it fails for a request-level reason, retry one channel at a time."""
    try:
        return await reader.channels(ids)
    except ProviderError as error:
        if error.code not in CHANNEL_LEVEL_FAILURES or len(ids) == 1:
            raise
    found: dict[str, Channel] = {}
    for single in ids:
        try:
            found |= await reader.channels([single])
        except ProviderError as error:
            if error.code not in CHANNEL_LEVEL_FAILURES:
                raise
    return found


def _points(videos: Sequence[Video]) -> list[VideoPoint]:
    return [
        VideoPoint(v.id, v.published_at, v.duration_seconds, v.views, v.language) for v in videos
    ]


def _hit(
    channel: Channel,
    videos: Sequence[Video],
    *,
    source: str,
    rank: int | None,
    rpm: tuple[Decimal, Decimal, str] | None,
    now: datetime,
) -> HitMetrics:
    points = _points(videos)
    monthly = monthly_long_views(points, now)
    ratio = max_outlier_ratio(points, channel.subscribers, now)
    income = income_range(monthly, rpm[0], rpm[1]) if rpm else (None, None)
    return HitMetrics(
        channel_id=channel.id,
        source=source,
        rank=rank,
        subscribers=channel.subscribers,
        monthly_long_views=monthly,
        income_low=income[0],
        income_high=income[1],
        shorts_share=shorts_share(points, now, WINDOW_DAYS),
        outlier_ratio_max=ratio,
        small_channel=channel.subscribers is not None
        and channel.subscribers < SMALL_CHANNEL_SUBSCRIBERS,
        traction=is_traction_channel(channel.subscribers, ratio),
        flags=channel_flags(channel.published_at, points, now),
        excluded_reason=None if language_ok(points) else "language",
    )


async def measure_hypothesis(
    engine: Engine,
    reader: YouTubeReader,
    hypothesis: dict[str, Any],
    run_id: UUID,
    config: Settings,
    now: datetime,
) -> dict[str, Any]:
    slug = hypothesis["slug"]
    published_after = now - timedelta(days=WINDOW_DAYS)
    appearances: dict[str, int] = {}
    first_rank: dict[str, int] = {}
    position = 0
    try:
        for query in hypothesis["queries"]:
            token: str | None = None
            for _ in range(config.subniche_search_pages):
                videos, token = await reader.search(query, published_after, token)
                for video in videos:
                    if not video.channel_id:
                        continue
                    position += 1
                    appearances[video.channel_id] = appearances.get(video.channel_id, 0) + 1
                    first_rank.setdefault(video.channel_id, position)
                if token is None:
                    break
        ranked = sorted(appearances, key=lambda cid: (-appearances[cid], first_rank[cid]))
        seeds: list[str] = list(hypothesis.get("seed_channels", []))
        chosen = list(dict.fromkeys([*seeds, *ranked[: config.subniche_channels_per_hypothesis]]))
        found: dict[str, Channel] = {}
        for start in range(0, len(chosen), BATCH_SIZE):
            found |= await _channels_of(reader, chosen[start : start + BATCH_SIZE])
        with engine.connect() as connection:
            rpm = rpm_range(connection, hypothesis["parent_niche_slug"])
        collected: list[tuple[Channel, Sequence[Video]]] = []
        hits: list[HitMetrics] = []
        for channel_id in chosen:
            channel = found.get(channel_id)
            if channel is None:
                continue
            try:
                videos_of = await reader.recent_videos(channel, RECENT_VIDEOS_LIMIT)
            except ProviderError as error:
                if error.code not in CHANNEL_LEVEL_FAILURES:
                    raise
                videos_of = ()
            collected.append((channel, videos_of))
            hits.append(
                _hit(
                    channel,
                    videos_of,
                    source="seed" if channel_id in seeds else "search",
                    rank=first_rank.get(channel_id),
                    rpm=rpm,
                    now=now,
                )
            )
    except ProviderError as error:
        return {"slug": slug, "stopped_reason": error.code, "partial": True}
    profile = build_profile(hits, rpm_source=rpm[2] if rpm else None)
    with engine.begin() as connection:
        save_measurement(
            connection,
            hypothesis_id=hypothesis["id"],
            run_id=run_id,
            now=now,
            channels=collected,
            hits=hits,
            profile=profile,
        )
    return {
        "slug": slug,
        "channels_seen": profile["channels_seen"],
        "stable": profile["stable_channels"],
        "traction": profile["traction_channels"],
        "signal": profile["signal"],
    }
