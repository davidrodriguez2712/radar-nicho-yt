# tests/subniche_samples.py
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.integrations.contracts import Channel, ProviderError, Video
from nicheradar.repositories import schema
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.subniche_discovery.contracts import HypothesisDraft

NOW = datetime(2026, 10, 31, 12, tzinfo=UTC)


def make_run(db: Connection, now: datetime = NOW) -> tuple[UUID, UUID, UUID]:
    """(discovery_run_id, analysis_run_id, profile_id)."""
    profile_id = seed_profile(db, CreatorProfile(), initial_catalog())
    analysis_id = insert_record(
        db,
        "analysis_runs",
        {
            "profile_id": profile_id,
            "mode": "live",
            "trigger": "subniche",
            "status": "queued",
            "configuration": {},
        },
    )
    run_id = uuid4()
    db.execute(
        sa.insert(schema.discovery_runs).values(
            id=run_id, analysis_run_id=analysis_id, status="running", started_at=now, stats={}
        )
    )
    return run_id, analysis_id, profile_id


def draft(
    slug: str = "history_revenge",
    queries: tuple[str, ...] = ("history revenge",),
    origin: str = "manual",
    seeds: tuple[str, ...] = (),
    parent: str | None = None,
) -> HypothesisDraft:
    return HypothesisDraft(
        slug=slug,
        label=slug.replace("_", " ").title(),
        family="history",
        parent_niche_slug=parent,
        queries=queries,
        origin=origin,
        source_input=None,
        seed_channel_ids=seeds,
    )


def channel(
    letter: str = "a",
    *,
    subscribers: int | None = 5_000,
    created_days_ago: int = 800,
    video_count: int = 20,
) -> Channel:
    return Channel(
        id="UC" + letter * 22,
        title=f"Channel {letter}",
        description="faceless history documentaries",
        subscribers=subscribers,
        uploads_playlist="UU" + letter * 22,
        published_at=NOW - timedelta(days=created_days_ago),
        video_count=video_count,
        total_views=1_000_000,
    )


def video(
    index: int,
    *,
    channel_letter: str = "a",
    days_ago: int = 10,
    duration: float = 900,
    views: int = 30_000,
    language: str | None = None,
) -> Video:
    return Video(
        id=f"vid{channel_letter}{index:03d}"[:11].ljust(11, "x"),
        channel_id="UC" + channel_letter * 22,
        title=f"Video {index}",
        published_at=NOW - timedelta(days=days_ago),
        views=views,
        duration_seconds=duration,
        language=language,
    )


class FakeReader:
    """Scripted YouTubeReader. `pages` maps query -> list of pages of videos."""

    def __init__(
        self,
        pages: dict[str, list[list[Video]]] | None = None,
        channels: dict[str, Channel] | None = None,
        uploads: dict[str, tuple[Video, ...]] | None = None,
        fail_search_after: int | None = None,
    ) -> None:
        self.pages = pages or {}
        self._channels = channels or {}
        self.uploads = uploads or {}
        self.search_calls = 0
        self.fail_search_after = fail_search_after
        self.videos_by_id: dict[str, Video] = {}
        self.handles: dict[str, Channel] = {}

    async def search(
        self, query: str, published_after: datetime, page_token: str | None
    ) -> tuple[list[Video], str | None]:
        if self.fail_search_after is not None and self.search_calls >= self.fail_search_after:
            raise ProviderError("subniche_daily_search_cap", not_sent=True)
        self.search_calls += 1
        pages = self.pages.get(query, [])
        index = int(page_token or 0)
        if index >= len(pages):
            return [], None
        return pages[index], str(index + 1) if index + 1 < len(pages) else None

    async def channels(self, ids: list[str]) -> dict[str, Channel]:
        return {i: self._channels[i] for i in ids if i in self._channels}

    async def channel_by_handle(self, handle: str) -> Channel | None:
        return self.handles.get(handle)

    async def recent_videos(self, channel: Channel, limit: int) -> tuple[Video, ...]:
        return self.uploads.get(channel.id, ())[:limit]

    async def video(self, video_id: str) -> Video | None:
        return self.videos_by_id.get(video_id)
