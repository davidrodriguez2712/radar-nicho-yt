"""Muestras compartidas para la lectura de tweets e imágenes."""

from typing import Any

import httpx
from pydantic import SecretStr

from nicheradar.config import Settings
from nicheradar.integrations.anthropic import AnthropicClient
from nicheradar.integrations.policies import Usage
from nicheradar.integrations.tweets import ImageData, Tweet, TweetReadError, TweetRef
from nicheradar.repositories.core import insert_record
from nicheradar.subniche_discovery.mentions import MENTIONS_TOOL, POLICY_DATA_TYPE
from tests.test_channel_analysis_advertising_match import llm_configuration
from tests.test_persistence import NOW as LLM_NOW

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 128
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 24
GIF = b"GIF89a" + b"\x00" * 32
TWEET_ID = "1850000000000000000"
VISION = llm_configuration()


def fx_payload(
    text: str = "Mira https://www.youtube.com/@historia_uno",
    photos: tuple[str, ...] = (),
    author: str = "autor_x",
    tweet_id: str = TWEET_ID,
) -> dict[str, Any]:
    return {
        "code": 200,
        "message": "OK",
        "tweet": {
            "id": tweet_id,
            "text": text,
            "author": {"screen_name": author, "name": "Autor"},
            "media": {"photos": [{"type": "photo", "url": url} for url in photos]},
        },
    }


class FakeTweetReader:
    """`TweetReader` guionizado: un tweet o un código de error, y fotos por URL."""

    def __init__(
        self,
        tweet: Tweet | None = None,
        error: str | None = None,
        photos: dict[str, ImageData] | None = None,
    ) -> None:
        self.tweet, self.error, self.photos = tweet, error, photos or {}
        self.reads: list[TweetRef] = []
        self.photo_calls: list[str] = []

    async def read(self, ref: TweetRef) -> Tweet:
        self.reads.append(ref)
        if self.error is not None or self.tweet is None:
            raise TweetReadError(self.error or "tweet_unavailable")
        return self.tweet

    async def photo(self, url: str) -> ImageData:
        self.photo_calls.append(url)
        if url not in self.photos:
            raise TweetReadError("photo_failed")
        return self.photos[url]


def vision_settings(**over: Any) -> Settings:
    values: dict[str, Any] = {
        "mode": "live",
        "subniche_enabled": True,
        "anthropic_enabled": True,
        "anthropic_api_key": SecretStr("secret-for-mocked-http-only"),
        "anthropic_vision_configuration": VISION,
    }
    return Settings(**(values | over))


def mention_payload(mentions: list[Any], **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "model": VISION.tariff.model,
        "stop_reason": "tool_use",
        "content": [{"type": "tool_use", "name": MENTIONS_TOOL, "input": {"mentions": mentions}}],
        "usage": {
            "input_tokens": 1500,
            "output_tokens": 120,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
    }
    return base | over


def mentions_client(
    mentions: list[Any], seen: list[httpx.Request] | None = None
) -> AnthropicClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(200, json=mention_payload(mentions))

    return AnthropicClient(
        SecretStr("secret-for-mocked-http-only"), transport=httpx.MockTransport(handler)
    )


def seed_lead_policies(connection: Any) -> None:
    for usage in (Usage.QUERY, Usage.STORAGE, Usage.DERIVED, Usage.LLM_PROCESSING):
        insert_record(
            connection,
            "provider_policies",
            {
                "provider": "anthropic",
                "operation": "lead_mentions",
                "data_type": POLICY_DATA_TYPE,
                "usage": usage.value,
                "version": "fixture-v1",
                "status": "enabled",
                "evidence_source": "synthetic test policy; not permission for real requests",
                "effective_at": LLM_NOW,
                "retention_seconds": 3600,
            },
        )
