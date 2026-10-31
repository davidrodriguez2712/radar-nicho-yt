# tests/test_subniche_youtube_params.py
import asyncio
from datetime import UTC, datetime

import httpx
from pydantic import SecretStr

from nicheradar.integrations.contracts import Operation
from nicheradar.integrations.youtube import YouTubeProvider

NOW = datetime(2026, 10, 31, 12, tzinfo=UTC)


def provider_capturing(seen: list[dict[str, str]]) -> YouTubeProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"items": []})

    return YouTubeProvider(
        SecretStr("key"), "scope", enabled=True, transport=httpx.MockTransport(handler)
    )


def test_search_forwards_window_language_and_duration() -> None:
    seen: list[dict[str, str]] = []
    asyncio.run(
        provider_capturing(seen).fetch(
            Operation.SEARCH,
            {
                "type": "video",
                "q": "history revenge",
                "order": "viewCount",
                "publishedAfter": "2026-08-02T12:00:00Z",
                "relevanceLanguage": "en",
                "videoDuration": "long",
                "maxResults": "50",
            },
            NOW,
        )
    )
    assert seen[0]["publishedAfter"] == "2026-08-02T12:00:00Z"
    assert seen[0]["relevanceLanguage"] == "en"
    assert seen[0]["videoDuration"] == "long"


def test_search_still_drops_unknown_parameters() -> None:
    seen: list[dict[str, str]] = []
    asyncio.run(
        provider_capturing(seen).fetch(
            Operation.SEARCH, {"type": "video", "q": "x", "safeSearch": "none"}, NOW
        )
    )
    assert "safeSearch" not in seen[0]


def test_hypothesis_proposal_operation_exists() -> None:
    assert Operation("hypothesis_proposal") is Operation.HYPOTHESIS_PROPOSAL
