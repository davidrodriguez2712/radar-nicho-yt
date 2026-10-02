import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine

from nicheradar.discovery.channel_analysis import (
    channel_view_rate,
    parse_channel_input,
    resolve_channel,
)
from nicheradar.domain.profile import CreatorProfile, VideoFormat
from nicheradar.integrations.contracts import Operation, ProviderError, Video
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
