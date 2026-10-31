# tests/test_anthropic_adapter.py
import asyncio
from decimal import Decimal
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from nicheradar.config import Settings
from nicheradar.integrations.anthropic import (
    ANTHROPIC_VERSION,
    ENDPOINT,
    AnthropicClient,
    anthropic_actual_usd,
)
from nicheradar.integrations.contracts import ProviderError
from tests.test_channel_analysis_advertising_match import llm_configuration

CONFIGURATION = llm_configuration()
TARIFF = CONFIGURATION.tariff  # model "fixture-model-pinned", 1 / .5 / 2 USD per million


def payload(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "model": TARIFF.model,
        "stop_reason": "tool_use",
        "content": [{"type": "tool_use", "name": "t", "input": {"a": 1}}],
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_read_input_tokens": 200,
            "cache_creation_input_tokens": 0,
        },
    }
    return base | over


def test_actual_usd_prices_uncached_cached_and_output_tokens() -> None:
    # Anthropic's input_tokens excludes cache reads: (1000 * 1 + 200 * 0.5 + 500 * 2) / 1e6
    assert anthropic_actual_usd(payload(), TARIFF) == Decimal("0.002100")


def test_actual_usd_accepts_a_dated_model_suffix_but_not_another_model() -> None:
    assert anthropic_actual_usd(payload(model=TARIFF.model + "-20261001"), TARIFF) is not None
    assert anthropic_actual_usd(payload(model="other-model"), TARIFF) is None


def test_actual_usd_is_none_when_billing_scope_is_unverified() -> None:
    created = payload(usage={**payload()["usage"], "cache_creation_input_tokens": 10})
    assert anthropic_actual_usd(created, TARIFF) is None
    huge = payload(usage={**payload()["usage"], "input_tokens": TARIFF.context_window_tokens + 1})
    assert anthropic_actual_usd(huge, TARIFF) is None
    assert anthropic_actual_usd({"model": TARIFF.model}, TARIFF) is None


def client(handler: Any) -> AnthropicClient:
    return AnthropicClient(
        SecretStr("secret-for-mocked-http-only"), transport=httpx.MockTransport(handler)
    )


def test_message_sends_headers_and_parses_with_the_given_function() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        return httpx.Response(200, json=payload())

    result = asyncio.run(
        client(handler).message(
            {"model": TARIFF.model}, CONFIGURATION, parse_fn=lambda p, t: p["stop_reason"]
        )
    )
    assert result == "tool_use"
    assert seen["url"] == ENDPOINT
    assert seen["headers"]["x-api-key"] == "secret-for-mocked-http-only"
    assert seen["headers"]["anthropic-version"] == ANTHROPIC_VERSION


def test_non_200_may_have_charged() -> None:
    with pytest.raises(ProviderError) as caught:
        asyncio.run(
            client(lambda r: httpx.Response(529, json={})).message(
                {"model": "m"}, CONFIGURATION, parse_fn=lambda p, t: p
            )
        )
    assert caught.value.code == "llm_http_error" and caught.value.may_have_charged


def test_oversized_request_is_refused_before_any_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("no request may be placed")

    with pytest.raises(ProviderError) as caught:
        asyncio.run(
            client(handler).message(
                {"model": "m", "pad": "x" * 70_000}, CONFIGURATION, parse_fn=lambda p, t: p
            )
        )
    assert caught.value.code == "llm_input_too_large"


def test_invalid_json_response_is_an_invalid_response_error() -> None:
    with pytest.raises(ProviderError) as caught:
        asyncio.run(
            client(lambda r: httpx.Response(200, content=b"not json")).message(
                {"model": "m"}, CONFIGURATION, parse_fn=lambda p, t: p
            )
        )
    assert caught.value.code == "llm_invalid_response"


def test_settings_read_anthropic_fields_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NR_ANTHROPIC_ENABLED", "true")
    monkeypatch.setenv("NR_ANTHROPIC_API_KEY", "secret-for-mocked-http-only")
    monkeypatch.setenv("NR_ANTHROPIC_CONFIGURATION", CONFIGURATION.model_dump_json())
    settings = Settings()
    assert settings.anthropic_enabled is True
    assert settings.anthropic_configuration is not None
    assert settings.anthropic_configuration.tariff.model == TARIFF.model
    assert "secret" not in repr(settings.anthropic_api_key)
