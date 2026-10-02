import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy import Engine

from nicheradar.discovery.channel_analysis import (
    channel_view_rate,
    discover_comparables,
    parse_channel_input,
    resolve_channel,
)
from nicheradar.domain.profile import CreatorProfile, VideoFormat
from nicheradar.integrations.contracts import (
    Batch,
    Channel,
    Coverage,
    Operation,
    Provenance,
    ProviderError,
    Video,
)
from nicheradar.integrations.synthetic import SyntheticProvider
from nicheradar.services.gateway import Gateway
from tests.test_persistence import NOW, seed_evidence


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("@scienceexplained", {"forHandle": "scienceexplained"}),
        ("https://www.youtube.com/@scienceexplained", {"forHandle": "scienceexplained"}),
        ("https://www.youtube.com/@scienceexplained/videos", {"forHandle": "scienceexplained"}),
        ("UC" + "a" * 22, {"id": "UC" + "a" * 22}),
        ("https://www.youtube.com/channel/" + "UC" + "a" * 22, {"id": "UC" + "a" * 22}),
    ],
)
def test_parse_channel_input_handles_and_ids(raw: str, expected: dict[str, str]) -> None:
    assert parse_channel_input(raw) == expected


def test_parse_channel_input_rejects_unsupported_shapes() -> None:
    with pytest.raises(ValueError, match="unsupported_channel_input"):
        parse_channel_input("https://www.youtube.com/c/SomeCustomName")
    with pytest.raises(ValueError, match="unsupported_channel_input"):
        parse_channel_input("https://www.youtube.com/user/LegacyName")
    with pytest.raises(ValueError, match="unsupported_channel_input"):
        parse_channel_input("not a channel at all")


@pytest.mark.postgres
def test_resolve_channel_not_found_raises_without_spending_other_budget(
    isolated_engine: Engine,
) -> None:
    # Synthetic provider's generic channel fixture always returns at least one channel for
    # CHANNELS/CHANNEL_SEARCH, keyed off the `family` parameter -- but `parse_channel_input`
    # never produces a `family` key, only `forHandle` or `id`. So the deterministic "not
    # found" trigger has to be a sentinel `forHandle`/`id` value instead: the `__none__`
    # branch added to SyntheticProvider below (see
    # test_synthetic_provider_returns_zero_channels_for_sentinel_handle) returns an empty
    # `channels` tuple when asked to resolve it.
    with isolated_engine.begin() as connection:
        ids = seed_evidence(connection)
    provider = SyntheticProvider()
    gateway = Gateway(
        isolated_engine,
        provider,
        ids["profile"],
        ids["run"],
        "synthetic",
        CreatorProfile(),
        {},
        {},
    )
    with pytest.raises(ProviderError, match="channel_not_found") as excinfo:
        asyncio.run(resolve_channel(gateway, "@__none__", datetime(2026, 9, 13, tzinfo=UTC)))
    # Signals to the caller that nothing was transmitted, so it is safe to retry/re-prompt
    # without worrying this already consumed a paid attempt.
    assert excinfo.value.not_sent is True
    # Exactly the one lookup was spent resolving the channel; no extra provider calls leaked.
    assert provider.calls == 1


def test_synthetic_provider_returns_zero_channels_for_sentinel_handle() -> None:
    provider = SyntheticProvider()
    batch = asyncio.run(
        provider.fetch(Operation.CHANNELS, {"forHandle": "__none__"}, datetime.now(UTC))
    )
    assert batch.channels == ()


def test_synthetic_provider_returns_zero_channels_for_sentinel_id() -> None:
    provider = SyntheticProvider()
    batch = asyncio.run(provider.fetch(Operation.CHANNELS, {"id": "__none__"}, datetime.now(UTC)))
    assert batch.channels == ()


def test_synthetic_provider_channels_populate_uploads_playlist() -> None:
    # fetch_channel_videos relies on channel.uploads_playlist being truthy to know which
    # playlist to pull videos from -- the synthetic fixture must populate it like real
    # YouTube channels do, or later discovery flows exercised against synthetic data would
    # silently always return no videos.
    provider = SyntheticProvider()
    batch = asyncio.run(provider.fetch(Operation.CHANNELS, {}, datetime.now(UTC)))
    assert all(channel.uploads_playlist for channel in batch.channels)
    assert all(channel.keywords for channel in batch.channels)


def test_channel_view_rate_is_median_views_per_day() -> None:
    videos = (
        Video(
            id="a",
            channel_id="c",
            title="t",
            published_at=NOW - timedelta(days=10),
            views=100,
            format=VideoFormat.LONG,
        ),
        Video(
            id="b",
            channel_id="c",
            title="t",
            published_at=NOW - timedelta(days=10),
            views=300,
            format=VideoFormat.LONG,
        ),
        Video(
            id="c", channel_id="c", title="t", published_at=None, views=500, format=VideoFormat.LONG
        ),  # no published_at: excluded
    )
    assert channel_view_rate(videos, NOW) == 20.0  # median(100/10, 300/10) = 20


def test_channel_view_rate_none_when_no_usable_video() -> None:
    videos = (
        Video(
            id="a",
            channel_id="c",
            title="t",
            published_at=None,
            views=None,
            format=VideoFormat.LONG,
        ),
    )
    assert channel_view_rate(videos, NOW) is None


class _FakeGateway:
    def __init__(self, channels: tuple[Channel, ...], *, raises: ProviderError | None = None):
        self._channels = channels
        self._raises = raises

    async def fetch(
        self, operation: Any, parameters: Any, now: datetime
    ) -> tuple[Batch, str, datetime]:
        if self._raises:
            raise self._raises

        return (
            Batch(
                provenance=Provenance(
                    provider="fake", operation=operation, auth_scope="x", fetched_at=now
                ),
                coverage=Coverage(returned=len(self._channels), selection_method="fake"),
                costs=(),
                channels=self._channels,
            ),
            "fake-request-id",
            now,
        )


def test_discover_comparables_dedupes_and_excludes_target() -> None:
    target = Channel(id="UC_target", title="Target")
    youtube_results = (target, Channel(id="UC_a", title="A"), Channel(id="UC_b", title="B"))
    vidiq_results = (Channel(id="UC_b", title="B"), Channel(id="UC_c", title="C"))
    discovery = asyncio.run(
        discover_comparables(
            cast(Gateway, _FakeGateway(youtube_results)),
            cast(Gateway, _FakeGateway(vidiq_results)),
            target,
            datetime.now(UTC),
        )
    )
    ids = {channel.id for channel in discovery.comparables}
    assert ids == {"UC_a", "UC_b", "UC_c"}  # target excluded, UC_b not duplicated
    assert discovery.vidiq_omitted is None


def test_discover_comparables_degrades_when_vidiq_budget_exhausted() -> None:
    target = Channel(id="UC_target", title="Target")
    youtube_results = (Channel(id="UC_a", title="A"),)
    discovery = asyncio.run(
        discover_comparables(
            cast(Gateway, _FakeGateway(youtube_results)),
            cast(Gateway, _FakeGateway((), raises=ProviderError("run_budget_exhausted"))),
            target,
            datetime.now(UTC),
        )
    )
    assert {channel.id for channel in discovery.comparables} == {"UC_a"}  # did not raise
    # The skip is visible, not silent, so the report can say vidIQ was omitted and why.
    assert discovery.vidiq_omitted == "budget_exhausted"


def test_discover_comparables_degrades_when_vidiq_rate_limited() -> None:
    # vidIQ maps HTTP 429 to "quota"; it must degrade to YouTube-only like the other
    # vidIQ budget codes, not discard the already-fetched YouTube results.
    discovery = asyncio.run(
        discover_comparables(
            cast(Gateway, _FakeGateway((Channel(id="UC_a", title="A"),))),
            cast(Gateway, _FakeGateway((), raises=ProviderError("quota", may_have_charged=True))),
            Channel(id="UC_target", title="Target"),
            datetime.now(UTC),
        )
    )
    assert {channel.id for channel in discovery.comparables} == {"UC_a"}
    assert discovery.vidiq_omitted == "budget_exhausted"


def test_discover_comparables_without_vidiq_gateway_is_not_marked_omitted() -> None:
    # Synthetic/YouTube-only runs never planned a vidIQ call; nothing was skipped.
    discovery = asyncio.run(
        discover_comparables(
            cast(Gateway, _FakeGateway((Channel(id="UC_a", title="A"),))),
            None,
            Channel(id="UC_target", title="Target"),
            datetime.now(UTC),
        )
    )
    assert discovery.vidiq_omitted is None


def test_compute_comparison_positions_target_against_real_comparables() -> None:
    from nicheradar.discovery.channel_analysis import compute_comparison

    target_videos = (
        Video(
            id="t1",
            channel_id="target",
            title="t",
            published_at=NOW - timedelta(days=10),
            views=500,
            format=VideoFormat.LONG,
        ),
    )
    comparable_videos: dict[str, tuple[Video, ...]] = {
        "UC_a": (
            Video(
                id="a1",
                channel_id="UC_a",
                title="t",
                published_at=NOW - timedelta(days=10),
                views=100,
                format=VideoFormat.LONG,
            ),
        ),
        "UC_b": (
            Video(
                id="b1",
                channel_id="UC_b",
                title="t",
                published_at=NOW - timedelta(days=10),
                views=2000,
                format=VideoFormat.LONG,
            ),
        ),
    }
    result = compute_comparison(
        target_videos, Channel(id="target", title="Target"), comparable_videos, NOW
    )
    assert result["target_view_rate"] == 50.0
    assert result["comparable_worst"] == 10.0
    assert result["comparable_best"] == 200.0
    assert result["target_position"] == "within"
    assert result["profit"]["status"] == "incomplete"  # no videos_per_month/advertising/cost given


def test_compute_comparison_handles_zero_comparables_without_crashing() -> None:
    from nicheradar.discovery.channel_analysis import compute_comparison

    target_videos = (
        Video(
            id="t1",
            channel_id="target",
            title="t",
            published_at=NOW - timedelta(days=10),
            views=500,
            format=VideoFormat.LONG,
        ),
    )
    result = compute_comparison(target_videos, Channel(id="target", title="Target"), {}, NOW)
    assert result["comparable_best"] is None
    assert result["comparable_worst"] is None
    assert result["target_position"] == "unknown"
    assert result["profit"]["status"] == "incomplete"
    assert "channel_view_rate" in result["profit"]["missing"]


def test_discover_comparables_queries_by_keyword_not_title() -> None:
    target = Channel(
        id="UC_target",
        title="Revenge Showdown",
        description="#revengestories #familydrama",
        keywords=("reddit revenge stories", "family drama"),
    )
    captured: dict[str, Any] = {}

    class CapturingGateway:
        async def fetch(
            self, operation: Any, parameters: Any, now: datetime
        ) -> tuple[Batch, str, datetime]:
            captured["parameters"] = parameters
            return (
                Batch(
                    provenance=Provenance(
                        provider="fake", operation=operation, auth_scope="x", fetched_at=now
                    ),
                    coverage=Coverage(returned=0, selection_method="fake"),
                    costs=(),
                    channels=(),
                ),
                "fake-request-id",
                now,
            )

    asyncio.run(
        discover_comparables(cast(Gateway, CapturingGateway()), None, target, datetime.now(UTC))
    )
    assert captured["parameters"]["q"] == "reddit revenge stories"
    assert captured["parameters"]["maxResults"] == "50"


def test_discover_comparables_falls_back_to_description_hashtag_then_title() -> None:
    no_keywords = Channel(
        id="UC_target", title="Revenge Showdown", description="Welcome! #revengestories here"
    )
    bare = Channel(id="UC_bare", title="Bare Title Channel")
    captured: list[str] = []

    class CapturingGateway:
        async def fetch(
            self, operation: Any, parameters: Any, now: datetime
        ) -> tuple[Batch, str, datetime]:
            captured.append(parameters["q"])
            return (
                Batch(
                    provenance=Provenance(
                        provider="fake", operation=operation, auth_scope="x", fetched_at=now
                    ),
                    coverage=Coverage(returned=0, selection_method="fake"),
                    costs=(),
                    channels=(),
                ),
                "fake-request-id",
                now,
            )

    asyncio.run(
        discover_comparables(
            cast(Gateway, CapturingGateway()), None, no_keywords, datetime.now(UTC)
        )
    )
    asyncio.run(
        discover_comparables(cast(Gateway, CapturingGateway()), None, bare, datetime.now(UTC))
    )
    assert captured[0] == "revengestories"
    assert captured[1] == "Bare Title Channel"


def test_compute_panorama_computes_real_metrics_across_comparables() -> None:
    from nicheradar.discovery.channel_analysis import compute_panorama

    comparable_videos: dict[str, tuple[Video, ...]] = {
        "UC_a": (
            Video(
                id="a1",
                channel_id="UC_a",
                title="t",
                published_at=NOW - timedelta(days=10),
                views=1000,
                format=VideoFormat.LONG,
            ),
        ),
        "UC_b": (
            Video(
                id="b1",
                channel_id="UC_b",
                title="t",
                published_at=NOW - timedelta(days=10),
                views=2000,
                format=VideoFormat.LONG,
            ),
        ),
    }
    panorama = compute_panorama(comparable_videos, NOW)
    assert panorama["status"] == "computed"
    assert panorama["metrics"]["videos"] == 2
    assert panorama["metrics"]["channels"] == 2


def test_compute_panorama_incomplete_when_no_comparable_videos() -> None:
    from nicheradar.discovery.channel_analysis import compute_panorama

    panorama = compute_panorama({}, NOW)
    assert panorama == {"status": "incomplete", "reason": "no_comparable_videos"}


def test_compute_panorama_skips_mixed_formats_without_crashing() -> None:
    from nicheradar.discovery.channel_analysis import compute_panorama

    comparable_videos: dict[str, tuple[Video, ...]] = {
        "UC_a": (
            Video(
                id="a1",
                channel_id="UC_a",
                title="t",
                published_at=NOW - timedelta(days=10),
                views=1000,
                format=VideoFormat.LONG,
            ),
        ),
        "UC_b": (
            Video(
                id="b1",
                channel_id="UC_b",
                title="t",
                published_at=NOW - timedelta(days=10),
                views=2000,
                format=VideoFormat.SHORTS,
            ),
        ),
    }
    panorama = compute_panorama(comparable_videos, NOW)
    assert panorama["status"] == "incomplete"
    assert panorama["reason"] == "mixed_formats_not_evaluable"
