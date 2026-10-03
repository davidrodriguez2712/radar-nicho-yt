import asyncio
from datetime import UTC, datetime
from typing import Any, cast

import httpx
import pytest
from pydantic import SecretStr

from nicheradar.discovery.channel_analysis import resolve_channel
from nicheradar.integrations.contracts import Batch, Operation
from nicheradar.integrations.youtube import YouTubeProvider
from nicheradar.services.gateway import Gateway

NOW = datetime(2026, 10, 3, 12, 0, 0, tzinfo=UTC)


def _provider(transport: httpx.MockTransport) -> YouTubeProvider:
    return YouTubeProvider(SecretStr("key"), "scope", enabled=True, transport=transport)


def fixture_transport(response_json: dict[str, Any]) -> httpx.MockTransport:
    """Create a mock transport that returns the given JSON response."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_json)

    return httpx.MockTransport(handler)


def test_search_channels_maps_nested_id_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["type"] == "channel"
        assert request.url.params["q"] == "science"
        return httpx.Response(
            200,
            json={
                "items": [
                    {"id": {"channelId": "UC123"}, "snippet": {"title": "Science Channel"}},
                ]
            },
        )

    provider = _provider(httpx.MockTransport(handler))
    batch = asyncio.run(
        provider.fetch(
            Operation.SEARCH,
            {"type": "channel", "q": "science", "maxResults": "10"},
            datetime.now(UTC),
        )
    )
    assert batch.channels[0].id == "UC123"
    assert batch.channels[0].title == "Science Channel"
    assert batch.costs[0].maximum == 100


def test_comment_threads_maps_top_level_comments() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["videoId"] == "vid1"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "snippet": {
                            "topLevelComment": {
                                "snippet": {"textDisplay": "Nice video", "likeCount": 4}
                            }
                        }
                    }
                ]
            },
        )

    provider = _provider(httpx.MockTransport(handler))
    batch = asyncio.run(
        provider.fetch(
            Operation.COMMENT_THREADS, {"videoId": "vid1", "maxResults": "20"}, datetime.now(UTC)
        )
    )
    assert batch.comments[0]["text"] == "Nice video"
    assert batch.comments[0]["like_count"] == 4
    assert batch.costs[0].maximum == 1


def test_video_categories_maps_id_to_title() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"items": [{"id": "24", "snippet": {"title": "Entertainment"}}]},
        )

    provider = _provider(httpx.MockTransport(handler))
    batch = asyncio.run(
        provider.fetch(Operation.VIDEO_CATEGORIES, {"regionCode": "US"}, datetime.now(UTC))
    )
    assert batch.category_labels == {"24": "Entertainment"}
    assert batch.costs[0].maximum == 1


def test_channels_maps_uploads_playlist_from_content_details() -> None:
    # fetch_channel_videos (Task 10) reads channel.uploads_playlist to know which playlist
    # to pull a channel's videos from -- this must come from channels.list's
    # contentDetails.relatedPlaylists.uploads.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "UC123",
                        "snippet": {"title": "Science Channel"},
                        "contentDetails": {
                            "relatedPlaylists": {"uploads": "UU123"},
                        },
                    },
                ]
            },
        )

    provider = _provider(httpx.MockTransport(handler))
    batch = asyncio.run(provider.fetch(Operation.CHANNELS, {"id": "UC123"}, datetime.now(UTC)))
    assert batch.channels[0].uploads_playlist == "UU123"


def test_unsupported_parameter_is_dropped_not_forwarded() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"items": []})

    provider = _provider(httpx.MockTransport(handler))
    asyncio.run(
        provider.fetch(
            Operation.SEARCH,
            {"type": "channel", "q": "science", "not_a_real_param": "x"},
            datetime.now(UTC),
        )
    )
    assert "not_a_real_param" not in captured["params"]


class _PassThroughGateway:
    """Hands resolve_channel's params straight to the real provider so the test sees the
    exact HTTP query string YouTubeProvider builds (policy/budget bookkeeping is covered
    elsewhere and is irrelevant to which query params survive the allow-list)."""

    def __init__(self, provider: YouTubeProvider):
        self.provider = provider

    async def fetch(
        self, operation: Operation, parameters: dict[str, Any], now: datetime
    ) -> tuple[Batch, str, bool]:
        return await self.provider.fetch(operation, parameters, now), "request-id", False


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("@scienceexplained", {"forHandle": "scienceexplained"}),
        ("https://www.youtube.com/@scienceexplained/videos", {"forHandle": "scienceexplained"}),
        ("UC" + "a" * 22, {"id": "UC" + "a" * 22}),
    ],
)
def test_resolve_channel_sends_identifying_param_over_real_http(
    raw: str, expected: dict[str, str]
) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        return httpx.Response(
            200,
            json={"items": [{"id": "UC" + "a" * 22, "snippet": {"title": "Science"}}]},
        )

    provider = _provider(httpx.MockTransport(handler))
    channel = asyncio.run(
        resolve_channel(cast(Gateway, _PassThroughGateway(provider)), raw, datetime.now(UTC))
    )
    assert channel.title == "Science"
    # channels.list requires one of id/forHandle/forUsername/mine; the allow-list must not
    # strip whichever identifying key parse_channel_input produced.
    assert {key: captured.get(key) for key in expected} == expected


def test_channels_list_requests_branding_settings_and_parses_keywords() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "UC1",
                        "snippet": {"title": "Revenge Showdown", "description": "desc"},
                        "statistics": {"subscriberCount": "100"},
                        "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}},
                        "brandingSettings": {
                            "channel": {"keywords": ('"Cheating wife" "Reddit stories" singleword')}
                        },
                    }
                ]
            },
        )

    provider = _provider(httpx.MockTransport(handler))
    batch = asyncio.run(provider.fetch(Operation.CHANNELS, {"id": "UC1"}, datetime.now(UTC)))
    assert "brandingSettings" in captured["request"].url.params["part"]
    channel = batch.channels[0]
    assert channel.keywords == ("Cheating wife", "Reddit stories", "singleword")


def test_channels_list_keywords_default_to_empty_tuple_when_absent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "UC2",
                        "snippet": {"title": "No Keywords Channel"},
                        "statistics": {"subscriberCount": "5"},
                        "contentDetails": {"relatedPlaylists": {"uploads": "UU2"}},
                    }
                ]
            },
        )

    provider = _provider(httpx.MockTransport(handler))
    batch = asyncio.run(provider.fetch(Operation.CHANNELS, {"id": "UC2"}, datetime.now(UTC)))
    assert batch.channels[0].keywords == ()


def test_channels_normalize_published_at_and_video_count() -> None:
    transport = fixture_transport(
        {
            "items": [
                {
                    "id": "UCabc",
                    "snippet": {"title": "T", "publishedAt": "2026-05-07T08:19:19.261163Z"},
                    "statistics": {"subscriberCount": "903", "videoCount": "184"},
                    "contentDetails": {"relatedPlaylists": {"uploads": "UUabc"}},
                }
            ]
        }
    )
    provider = YouTubeProvider(
        api_key=SecretStr("k"), auth_scope="scope", enabled=True, transport=transport
    )
    batch = asyncio.run(provider.fetch(Operation.CHANNELS, {"id": "UCabc"}, NOW))
    channel = batch.channels[0]
    assert channel.published_at == datetime(2026, 5, 7, 8, 19, 19, 261163, tzinfo=UTC)
    assert channel.video_count == 184
