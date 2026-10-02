import asyncio
from datetime import UTC, datetime

import httpx
from pydantic import SecretStr

from nicheradar.integrations.contracts import Operation
from nicheradar.integrations.youtube import YouTubeProvider


def _provider(transport: httpx.MockTransport) -> YouTubeProvider:
    return YouTubeProvider(SecretStr("key"), "scope", enabled=True, transport=transport)


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
