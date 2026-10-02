import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine

from nicheradar.discovery.channel_analysis import parse_channel_input, resolve_channel
from nicheradar.domain.profile import CreatorProfile
from nicheradar.integrations.contracts import Operation, ProviderError
from nicheradar.integrations.synthetic import SyntheticProvider
from nicheradar.services.gateway import Gateway
from tests.test_persistence import seed_evidence


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
