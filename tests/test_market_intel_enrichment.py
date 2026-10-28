# tests/test_market_intel_enrichment.py
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, Engine

from nicheradar.config import Settings
from nicheradar.integrations.contracts import Channel, ProviderError, Video
from nicheradar.integrations.retention import expire
from nicheradar.market_intel.context import RunContext
from nicheradar.market_intel.contracts import ListingCard, ListingDetail
from nicheradar.market_intel.enrichment import (
    ENRICH_TTL,
    SNAPSHOT_RETENTION,
    pending_enrichment,
    save_snapshot,
    stage_enrich,
)
from nicheradar.market_intel.ingest import apply_detail, upsert_cards
from nicheradar.market_intel.sources.factory import build_source
from nicheradar.repositories.schema import listing_channel_snapshots as snapshots

NOW = datetime(2026, 10, 28, 12, tzinfo=UTC)
SOURCE = "dealbaron"


def channel_id(letter: str) -> str:
    return "UC" + letter * 22


def seed(
    connection: Connection, external_id: str, *, income: int | None = 500, uc: str | None = "a"
) -> UUID:
    card = ListingCard(
        external_id=external_id,
        url=f"https://dealbaron.test/listing/{external_id}",
        title=f"Channel {external_id}",
        category="Games",
        subscribers=10_000,
        income_monthly_usd=Decimal(income) if income is not None else None,
    )
    upsert_cards(connection, SOURCE, [card], NOW, NOW.date())
    url = f"https://www.youtube.com/channel/{channel_id(uc)}" if uc else "https://youtube.com/@x"
    apply_detail(
        connection,
        SOURCE,
        ListingDetail(external_id=external_id, title="t", channel_url=url),
        NOW,
        NOW.date(),
    )
    found: UUID = connection.execute(
        sa.text("SELECT id FROM marketplace_listings WHERE external_id = :e"), {"e": external_id}
    ).scalar_one()
    return found


@pytest.mark.postgres
def test_pending_takes_active_listings_with_a_channel_id_income_first(db: Connection) -> None:
    rich = seed(db, "rich", income=900, uc="a")
    poor = seed(db, "poor", income=100, uc="b")
    none = seed(db, "none", income=None, uc="c")
    seed(db, "handle_only", uc=None)  # @handle URL: no channel id to batch
    ids = [item["id"] for item in pending_enrichment(db, SOURCE, 10, NOW)]
    assert ids == [rich, poor, none]
    assert len(pending_enrichment(db, SOURCE, 2, NOW)) == 2


@pytest.mark.postgres
def test_a_fresh_snapshot_is_not_refetched_until_the_ttl_passes(db: Connection) -> None:
    listing = seed(db, "one")
    save_snapshot(db, listing, channel_id("a"), None, (), NOW - timedelta(days=5))
    assert pending_enrichment(db, SOURCE, 10, NOW) == []
    later = NOW - timedelta(days=5) + ENRICH_TTL + timedelta(days=1)
    assert [i["id"] for i in pending_enrichment(db, SOURCE, 10, later)] == [listing]


def video(index: int, *, days_ago: int, duration: float = 600, views: int = 100) -> Video:
    return Video(
        id=f"video{index:02d}",
        channel_id=channel_id("a"),
        title=f"title {index}",
        published_at=NOW - timedelta(days=days_ago),
        views=views,
        duration_seconds=duration,
    )


def channel(**over: object) -> Channel:
    base: dict[str, object] = {
        "id": channel_id("a"),
        "title": "Vintage",
        "subscribers": 2000,
        "country": "US",
        "published_at": NOW - timedelta(days=900),
        "video_count": 80,
        "total_views": 1_500_000,
    }
    return Channel.model_validate(base | over)


@pytest.mark.postgres
def test_a_snapshot_keeps_the_channel_facts_and_the_ten_latest_videos(db: Connection) -> None:
    listing = seed(db, "one")
    videos = tuple(video(i, days_ago=i * 3) for i in range(14))
    save_snapshot(db, listing, channel_id("a"), channel(), tuple(reversed(videos)), NOW)
    row = db.execute(sa.select(snapshots)).mappings().one()
    assert row["status"] == "ok" and row["title"] == "Vintage" and row["country"] == "US"
    assert row["subscribers"] == 2000 and row["total_views"] == 1_500_000
    assert row["video_count"] == 80 and row["channel_created_at"] == NOW - timedelta(days=900)
    recent = row["recent_videos"]
    assert [v["video_id"] for v in recent] == [f"video{i:02d}" for i in range(10)]  # newest first
    assert recent[0]["duration_seconds"] == 600 and recent[0]["views"] == 100
    assert row["retain_until"] == NOW + SNAPSHOT_RETENTION  # YouTube data: 30 days at most


@pytest.mark.postgres
def test_a_missing_channel_is_recorded_so_it_is_not_asked_again(db: Connection) -> None:
    listing = seed(db, "gone")
    save_snapshot(db, listing, channel_id("a"), None, (), NOW)
    row = db.execute(sa.select(snapshots)).mappings().one()
    assert row["status"] == "not_found" and row["title"] is None and row["recent_videos"] == []


@pytest.mark.postgres
def test_expiry_and_listing_deletion_remove_snapshots(db: Connection) -> None:
    listing = seed(db, "one")
    save_snapshot(db, listing, channel_id("a"), channel(), (), NOW)
    expire(db, NOW + SNAPSHOT_RETENTION - timedelta(seconds=1))
    assert db.execute(sa.select(sa.func.count()).select_from(snapshots)).scalar_one() == 1
    expire(db, NOW + SNAPSHOT_RETENTION + timedelta(seconds=1))
    assert db.execute(sa.select(sa.func.count()).select_from(snapshots)).scalar_one() == 0


class FakeFetcher:
    def __init__(
        self, known: dict[str, Channel], videos: dict[str, tuple[Video, ...]] | None = None
    ):
        self.known = known
        self.videos = videos or {}
        self.batches: list[list[str]] = []
        self.fail_videos_for: set[str] = set()

    async def channels(self, channel_ids: list[str]) -> dict[str, Channel]:
        self.batches.append(sorted(channel_ids))
        return {i: self.known[i] for i in channel_ids if i in self.known}

    async def recent_videos(self, found: Channel) -> tuple[Video, ...]:
        if found.id in self.fail_videos_for:
            raise ProviderError("quota")
        return self.videos.get(found.id, ())


def context(engine: Engine, config: Settings, mode: str = "live") -> RunContext:
    return RunContext(
        engine=engine,
        config=config,
        source=build_source(Settings(mode="synthetic")),
        run_id=uuid4(),
        analysis_run={"id": uuid4(), "profile_id": uuid4(), "mode": mode},
        owner="worker",
        started_at=NOW,
        clock=lambda: NOW,
    )


LIVE = Settings(
    mode="live",
    youtube_live_enabled=True,
    youtube_api_key=None,  # hermetic: never inherit the owner's .env key
    market_intel_enrich_cap_per_run=10,
)


@pytest.mark.postgres
def test_the_stage_is_off_unless_live_with_youtube_and_a_cap(isolated_engine: Engine) -> None:
    assert stage_enrich(context(isolated_engine, LIVE, "synthetic")) == {
        "skipped": "synthetic_mode"
    }
    for config in (
        Settings(mode="live", youtube_live_enabled=True),  # cap defaults to 0
        Settings(mode="live", market_intel_enrich_cap_per_run=5),  # youtube disabled
    ):
        assert stage_enrich(context(isolated_engine, config)) == {"skipped": "youtube_not_enabled"}


@pytest.mark.postgres
def test_the_stage_without_credentials_reports_a_partial_skip(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        seed(connection, "one")
    assert stage_enrich(context(isolated_engine, LIVE)) == {
        "skipped": "authentication_required",
        "partial": True,
    }


@pytest.mark.postgres
def test_the_stage_batches_channels_and_saves_each_outcome(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        ok = seed(connection, "ok", income=900, uc="a")
        gone = seed(connection, "gone", income=500, uc="b")
        shared = seed(connection, "shared", income=100, uc="a")  # same channel, two listings
    fetcher = FakeFetcher(
        {channel_id("a"): channel()},
        {channel_id("a"): tuple(video(i, days_ago=i) for i in range(3))},
    )
    result = stage_enrich(context(isolated_engine, LIVE), fetcher)
    assert result == {"pending": 3, "saved": 3, "not_found": 1}
    assert fetcher.batches == [[channel_id("a"), channel_id("b")]]  # one call, ids deduplicated
    with isolated_engine.connect() as connection:
        rows = {r["listing_id"]: r for r in connection.execute(sa.select(snapshots)).mappings()}
    assert rows[ok]["status"] == rows[shared]["status"] == "ok"
    assert rows[gone]["status"] == "not_found"
    assert len(rows[ok]["recent_videos"]) == 3
    # Nothing left to do within the TTL.
    again = stage_enrich(context(isolated_engine, LIVE), fetcher)
    assert again == {"pending": 0, "saved": 0, "not_found": 0}


@pytest.mark.postgres
def test_a_quota_error_stops_the_stage_and_keeps_what_was_saved(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        first = seed(connection, "first", income=900, uc="a")
        seed(connection, "second", income=500, uc="b")
        seed(connection, "third", income=100, uc="c")
    fetcher = FakeFetcher(
        {
            channel_id("a"): channel(),
            channel_id("b"): channel(id=channel_id("b")),
            channel_id("c"): channel(id=channel_id("c")),
        }
    )
    fetcher.fail_videos_for = {channel_id("b")}
    result = stage_enrich(context(isolated_engine, LIVE), fetcher)
    assert result["saved"] == 1 and result["stopped_reason"] == "quota" and result["partial"]
    with isolated_engine.connect() as connection:
        saved = list(connection.execute(sa.select(snapshots.c.listing_id)).scalars())
    assert saved == [first]


@pytest.mark.postgres
def test_the_cap_limits_how_many_channels_are_fetched(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        for index, letter in enumerate("abcd"):
            seed(connection, f"l{index}", income=500 - index, uc=letter)
    known = {channel_id(x): channel(id=channel_id(x)) for x in "abcd"}
    config = LIVE.model_copy(update={"market_intel_enrich_cap_per_run": 2})
    result = stage_enrich(context(isolated_engine, config), FakeFetcher(known))
    assert result["saved"] == 2 and result["pending"] == 2


class FlakyFetcher(FakeFetcher):
    """Fails one channel's uploads (or a whole batch) with a code that blames a single request."""

    def __init__(self, *args: object, bad_batch_code: str | None = None, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.bad_batch_code = bad_batch_code
        self.bad_uploads: dict[str, str] = {}

    async def channels(self, channel_ids: list[str]) -> dict[str, Channel]:
        if self.bad_batch_code and len(channel_ids) > 1:
            self.batches.append(sorted(channel_ids))
            raise ProviderError(self.bad_batch_code)
        return await super().channels(channel_ids)

    async def recent_videos(self, found: Channel) -> tuple[Video, ...]:
        if found.id in self.bad_uploads:
            raise ProviderError(self.bad_uploads[found.id])
        return await super().recent_videos(found)


def three_channels() -> dict[str, Channel]:
    return {channel_id(x): channel(id=channel_id(x)) for x in "abc"}


@pytest.mark.postgres
@pytest.mark.parametrize("code", ["provider_response_failed", "unknown_charge"])
def test_one_channel_whose_uploads_fail_does_not_stop_the_stage(
    isolated_engine: Engine, code: str
) -> None:
    with isolated_engine.begin() as connection:
        for index, letter in enumerate("abc"):
            seed(connection, f"l{index}", income=900 - index, uc=letter)
    fetcher = FlakyFetcher(three_channels())
    fetcher.bad_uploads = {channel_id("b"): code}
    result = stage_enrich(context(isolated_engine, LIVE), fetcher)
    assert result == {"pending": 3, "saved": 3, "not_found": 0, "videos_failed": 1}
    with isolated_engine.connect() as connection:
        rows = list(connection.execute(sa.select(snapshots)).mappings())
    by_channel = {r["youtube_channel_id"]: r for r in rows}
    assert by_channel[channel_id("b")]["status"] == "ok"  # the channel facts are still real
    assert by_channel[channel_id("b")]["recent_videos"] == []
    assert by_channel[channel_id("b")]["video_count"] == 80  # tells "no videos" from "fetch failed"


@pytest.mark.postgres
def test_a_failing_batch_is_retried_one_channel_at_a_time(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        for index, letter in enumerate("abc"):
            seed(connection, f"l{index}", income=900 - index, uc=letter)
    fetcher = FlakyFetcher(three_channels(), bad_batch_code="provider_response_failed")
    result = stage_enrich(context(isolated_engine, LIVE), fetcher)
    assert result == {"pending": 3, "saved": 3, "not_found": 0}
    assert fetcher.batches[0] == [channel_id(x) for x in "abc"]
    assert [b for b in fetcher.batches[1:]] == [[channel_id(x)] for x in "abc"]


@pytest.mark.postgres
def test_a_quota_error_on_uploads_still_stops_the_whole_stage(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        for index, letter in enumerate("abc"):
            seed(connection, f"l{index}", income=900 - index, uc=letter)
    fetcher = FlakyFetcher(three_channels())
    fetcher.bad_uploads = {channel_id("b"): "quota"}
    result = stage_enrich(context(isolated_engine, LIVE), fetcher)
    assert result["stopped_reason"] == "quota" and result["saved"] == 1
