"""YouTube access for sub-niche discovery: the Gateway enforces policy, ledger and idempotency."""

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, Engine, func, select

from nicheradar.config import Settings
from nicheradar.integrations.contracts import Channel, Operation, ProviderError, Video
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import get_profile
from nicheradar.services.budget import Limits
from nicheradar.services.channel_analysis_providers import channel_analysis_youtube_tariffs
from nicheradar.services.gateway import Gateway
from nicheradar.services.youtube_enrichment import youtube_provider

SEARCH_UNIT = "youtube_search_quota"
SEARCH_COST = Decimal(100)
MAX_CALLS_PER_RUN = 10_000


class YouTubeReader(Protocol):
    async def search(
        self, query: str, published_after: datetime, page_token: str | None
    ) -> tuple[list[Video], str | None]: ...

    async def channels(self, ids: list[str]) -> dict[str, Channel]: ...

    async def channel_by_handle(self, handle: str) -> Channel | None: ...

    async def recent_videos(self, channel: Channel, limit: int) -> tuple[Video, ...]: ...

    async def video(self, video_id: str) -> Video | None: ...


def subniche_youtube_limits(config: Settings) -> dict[str, Limits]:
    return {
        SEARCH_UNIT: Limits(
            operation=SEARCH_COST,
            run=Decimal(config.subniche_search_quota_per_run),
            week=Decimal(config.subniche_search_quota_per_week),
            period=Decimal(config.subniche_search_quota_per_month),
        ),
        "youtube_quota": Limits(
            operation=Decimal(1),
            run=Decimal(config.subniche_detail_quota_per_run),
            week=Decimal(config.subniche_detail_quota_per_week),
            period=Decimal(config.subniche_detail_quota_per_month),
        ),
    }


def search_units_used_today(connection: Connection, now: datetime, timezone: str) -> Decimal:
    local = now.astimezone(ZoneInfo(timezone))
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return Decimal(
        connection.execute(
            select(func.coalesce(func.sum(s.cost_reservations.c.amount), 0)).where(
                s.cost_reservations.c.unit == SEARCH_UNIT,
                s.cost_reservations.c.status.in_(["reserved", "unknown_charge", "confirmed"]),
                s.cost_reservations.c.created_at >= day_start,
            )
        ).scalar_one()
    )


class GatewayReader:
    def __init__(
        self,
        gateway: Gateway,
        engine: Engine,
        config: Settings,
        clock: Callable[[], datetime],
    ) -> None:
        self.gateway, self.engine, self.config, self.clock = gateway, engine, config, clock

    async def search(
        self, query: str, published_after: datetime, page_token: str | None
    ) -> tuple[list[Video], str | None]:
        now = self.clock()
        with self.engine.connect() as connection:
            used = search_units_used_today(connection, now, self.config.timezone)
        if used + SEARCH_COST > self.config.subniche_search_units_per_day:
            raise ProviderError("subniche_daily_search_cap", not_sent=True)
        parameters: dict[str, Any] = {
            "type": "video",
            "q": query,
            "order": "viewCount",
            "publishedAfter": published_after.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "relevanceLanguage": "en",
            "videoDuration": "long",
            "maxResults": "50",
        }
        if page_token:
            parameters["pageToken"] = page_token
        batch, _, _ = await self.gateway.fetch(Operation.SEARCH, parameters, now)
        return list(batch.videos), batch.coverage.next_page

    async def channels(self, ids: list[str]) -> dict[str, Channel]:
        batch, _, _ = await self.gateway.fetch(
            Operation.CHANNELS, {"id": ",".join(ids)}, self.clock()
        )
        return {channel.id: channel for channel in batch.channels}

    async def channel_by_handle(self, handle: str) -> Channel | None:
        batch, _, _ = await self.gateway.fetch(
            Operation.CHANNELS, {"forHandle": handle}, self.clock()
        )
        return batch.channels[0] if batch.channels else None

    async def recent_videos(self, channel: Channel, limit: int) -> tuple[Video, ...]:
        if not channel.uploads_playlist or channel.video_count == 0:
            return ()
        uploads, _, _ = await self.gateway.fetch(
            Operation.UPLOADS,
            {"playlistId": channel.uploads_playlist, "maxResults": str(min(limit, 50))},
            self.clock(),
        )
        ids = [video.id for video in uploads.videos][:limit]
        if not ids:
            return ()
        batch, _, _ = await self.gateway.fetch(
            Operation.VIDEOS, {"id": ",".join(ids)}, self.clock()
        )
        return batch.videos

    async def video(self, video_id: str) -> Video | None:
        batch, _, _ = await self.gateway.fetch(Operation.VIDEOS, {"id": video_id}, self.clock())
        return batch.videos[0] if batch.videos else None


def build_reader(
    engine: Engine, config: Settings, run: dict[str, Any], clock: Callable[[], datetime]
) -> GatewayReader:
    """Raises ProviderError when YouTube is not configured; the Gateway enforces quota/policy."""
    youtube = youtube_provider(config)
    with engine.connect() as connection:
        profile_id, _, profile = get_profile(connection)
    gateway = Gateway(
        engine,
        youtube,
        profile_id,
        run["id"],
        str(config.youtube_auth_scope),
        profile,
        subniche_youtube_limits(config),
        channel_analysis_youtube_tariffs(),
        maximum_calls=MAX_CALLS_PER_RUN,
    )
    return GatewayReader(gateway, engine, config, clock)
