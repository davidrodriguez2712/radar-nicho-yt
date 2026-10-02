import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from nicheradar.domain.profile import VideoFormat
from nicheradar.integrations.contracts import Operation, ProviderError
from nicheradar.integrations.vidiq import MCPTransport, VidIQProvider
from nicheradar.integrations.youtube import YouTubeProvider

NOW = datetime(2026, 9, 13, tzinfo=UTC)


class FixtureTools:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, name: str, parameters: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, parameters))
        return self.payload


def test_vidiq_recent_defaults_and_nulls() -> None:
    transport = FixtureTools(
        {
            "channelId": "synthetic-channel",
            "videoFormat": "short",
            "videos": [
                {
                    "videoId": "synthetic-video",
                    "title": "A fixture",
                    "publishedAt": NOW.isoformat(),
                    "viewCount": 0,
                    "breakoutScore": None,
                    "vph": None,
                },
            ],
        }
    )
    batch = asyncio.run(
        VidIQProvider(transport, "test").fetch(
            Operation.CHANNEL_VIDEOS,
            {"channelId": "synthetic-channel", "videoFormat": "short"},
            NOW,
        )
    )
    assert transport.calls[0][0] == "vidiq_channel_videos"
    assert transport.calls[0][1]["popular"] is False
    assert batch.videos[0].views == 0
    assert batch.videos[0].format == VideoFormat.SHORTS
    assert batch.videos[0].language is None
    assert batch.videos[0].metrics["provider_breakout"].value is None
    assert not batch.coverage.complete
    assert batch.coverage.next_page is None


def test_vidiq_search_country_is_not_audience_and_unknown_growth() -> None:
    transport = FixtureTools(
        {
            "total": 10000,
            "channels": [
                {
                    "channelId": "fixture",
                    "channelTitle": "Fixture",
                    "subscriberCount": 0,
                    "languages": "en, es",
                    "country": "US",
                }
            ],
        }
    )
    batch = asyncio.run(VidIQProvider(transport, "test").fetch(Operation.CHANNEL_SEARCH, {}, NOW))
    assert batch.coverage.returned == 1
    assert batch.coverage.reported_total == 10000
    assert batch.channels[0].audience_countries == ()
    assert batch.channels[0].content_languages == ("en", "es")
    assert batch.channels[0].metrics["subsGrowth30d"].unit == "provider_unspecified_growth"


def test_vidiq_outliers_do_not_infer_short_from_duration() -> None:
    transport = FixtureTools(
        {
            "videos": [
                {
                    "videoId": "fixture",
                    "channelId": "fixture-channel",
                    "videoTitle": "Fixture",
                    "videoPublishedAt": NOW.timestamp(),
                    "videoType": None,
                    "videoDuration": 30,
                    "viewCount": 1000,
                    "breakoutScore": 10,
                }
            ]
        }
    )
    batch = asyncio.run(VidIQProvider(transport, "test").fetch(Operation.OUTLIERS, {}, NOW))
    assert batch.videos[0].format == VideoFormat.UNKNOWN
    assert batch.coverage.selection_method == "outliers"


@pytest.mark.parametrize("video_format", ["long", "short"])
def test_vidiq_outliers_translate_discovery_filters_to_real_contract(video_format: str) -> None:
    transport = FixtureTools({"videos": []})
    parameters = {
        "query": "astronomy",
        "family": "science",
        "videoFormat": video_format,
        "language": "en",
        "limit": 10,
    }
    asyncio.run(VidIQProvider(transport, "test").fetch(Operation.OUTLIERS, parameters, NOW))
    assert transport.calls == [
        (
            "vidiq_outliers",
            {"keyword": "astronomy", "contentType": video_format, "language": "en", "limit": 10},
        )
    ]
    assert parameters["query"] == "astronomy"  # Do not mutate the gateway's cache-key inputs.
    assert parameters["videoFormat"] == video_format


@pytest.mark.parametrize(
    "parameters",
    [
        {"query": "astronomy", "keyword": "decoration"},
        {"videoFormat": "short", "contentType": "long"},
    ],
)
def test_vidiq_outliers_reject_conflicting_filters_before_send(parameters: dict[str, str]) -> None:
    transport = FixtureTools({"videos": []})
    with pytest.raises(ProviderError, match="conflicting_parameters") as caught:
        asyncio.run(VidIQProvider(transport, "test").fetch(Operation.OUTLIERS, parameters, NOW))
    assert caught.value.not_sent
    assert not caught.value.may_have_charged
    assert transport.calls == []


def test_vidiq_outliers_native_names_and_identical_aliases_are_supported() -> None:
    transport = FixtureTools({"videos": []})
    provider = VidIQProvider(transport, "test")
    native = {"keyword": "astronomy", "contentType": "short"}
    asyncio.run(provider.fetch(Operation.OUTLIERS, native, NOW))
    asyncio.run(
        provider.fetch(
            Operation.OUTLIERS, native | {"query": "astronomy", "videoFormat": "short"}, NOW
        )
    )
    assert transport.calls == [("vidiq_outliers", native), ("vidiq_outliers", native)]


def test_vidiq_keywords_and_balance() -> None:
    transport = FixtureTools({"relatedKeywords": [{"keyword": "fixture", "volume": None}]})
    batch = asyncio.run(VidIQProvider(transport, "test").fetch(Operation.KEYWORDS, {}, NOW))
    assert batch.keywords[0]["volume"] is None
    transport.payload = {
        "type": "limited",
        "renewableCredits": 135,
        "addOnCredits": 20,
        "maxRenewableCredits": 150,
        "renewableResetsAt": NOW.isoformat(),
        "totalCredits": 155,
    }
    balance = asyncio.run(
        VidIQProvider(transport, "test").fetch(Operation.BALANCE, {}, NOW)
    ).balance
    assert balance is not None
    assert balance.recurring_allocation == 150
    assert balance.additional == 20
    transport.payload["totalCredits"] = 170
    with pytest.raises(ProviderError, match="contract_mismatch"):
        asyncio.run(VidIQProvider(transport, "test").fetch(Operation.BALANCE, {}, NOW))


def test_mcp_disabled_and_no_auth_make_no_request() -> None:
    with pytest.raises(ProviderError, match="integration_disabled"):
        asyncio.run(MCPTransport().call("vidiq_balance", {}))
    with pytest.raises(ProviderError, match="authentication_required"):
        asyncio.run(MCPTransport(enabled=True).call("vidiq_balance", {}))


def test_mcp_actual_sdk_auth_failure_is_redacted() -> None:
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(401)

    client = MCPTransport(
        auth=httpx.BasicAuth("fixture", "synthetic-secret"),
        enabled=True,
        transport=httpx.MockTransport(respond),
    )
    with pytest.raises(ProviderError, match="authentication_required") as exc:
        asyncio.run(client.call("vidiq_balance", {}))
    assert "synthetic-secret" not in str(exc.value)
    assert not exc.value.retry_safe
    assert len(calls) == 1


def test_youtube_pages_duplicates_missing_resources_and_format() -> None:
    requested_pages = []

    def respond(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("pageToken")
        requested_pages.append(page)
        assert "key" not in request.url.params
        item = {
            "id": "playlist-item",
            "snippet": {"title": "Fixture", "videoOwnerChannelId": "fixture-channel"},
            "contentDetails": {"videoId": "fixture-video", "videoPublishedAt": NOW.isoformat()},
        }
        return httpx.Response(
            200,
            json={
                "items": [item, item, {"id": "deleted-resource", "snippet": {}}],
                "nextPageToken": "page-2",
            }
            if not page
            else {"items": []},
        )

    provider = YouTubeProvider(
        SecretStr("synthetic-key"), "test", enabled=True, transport=httpx.MockTransport(respond)
    )
    first = asyncio.run(provider.fetch(Operation.UPLOADS, {"playlistId": "fixture-playlist"}, NOW))
    assert len(first.videos) == 1
    assert first.videos[0].format == VideoFormat.UNKNOWN
    assert first.videos[0].channel_id == "fixture-channel"
    assert first.coverage.next_page == "page-2"
    assert requested_pages == [None]
    second = asyncio.run(
        provider.fetch(
            Operation.UPLOADS,
            {"playlistId": "fixture-playlist", "pageToken": first.coverage.next_page},
            NOW,
        )
    )
    assert not second.videos
    assert requested_pages == [None, "page-2"]


def test_youtube_channel_uploads_and_video_metadata() -> None:
    provider = YouTubeProvider(None, "test")
    channels = provider.normalize(
        Operation.CHANNELS,
        {
            "items": [
                {
                    "id": "fixture",
                    "snippet": {"title": "Fixture", "country": "US"},
                    "statistics": {"subscriberCount": "0", "hiddenSubscriberCount": True},
                    "contentDetails": {"relatedPlaylists": {"uploads": "fixture-uploads"}},
                }
            ]
        },
        NOW,
    )
    assert channels.channels[0].uploads_playlist == "fixture-uploads"
    assert channels.channels[0].subscribers is None
    videos = provider.normalize(
        Operation.VIDEOS,
        {
            "items": [
                {
                    "id": "fixture-video",
                    "snippet": {
                        "title": "Fixture",
                        "channelId": "fixture",
                        "publishedAt": NOW.isoformat(),
                        "defaultAudioLanguage": "en",
                    },
                    "statistics": {"viewCount": "0"},
                    "contentDetails": {"duration": "PT30S"},
                }
            ]
        },
        NOW,
    )
    assert videos.videos[0].views == 0
    assert videos.videos[0].format == VideoFormat.UNKNOWN
    assert videos.videos[0].duration_seconds == 30
    assert videos.costs[0].actual == 1


@pytest.mark.parametrize("status,code", [(401, "authentication_required"), (429, "quota")])
def test_youtube_auth_and_quota_do_not_retry_or_expose_key(status: int, code: str) -> None:
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json={"error": {}})

    provider = YouTubeProvider(
        SecretStr("secret-fixture-key"),
        "test",
        enabled=True,
        transport=httpx.MockTransport(respond),
    )
    with pytest.raises(ProviderError, match=code) as exc:
        asyncio.run(provider.fetch(Operation.VIDEOS, {"id": "fixture"}, NOW))
    assert "secret-fixture-key" not in str(exc.value)
    assert len(calls) == 1
