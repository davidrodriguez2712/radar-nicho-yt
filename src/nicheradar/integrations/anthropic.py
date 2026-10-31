"""Bounded Anthropic Messages adapter. No default model, price or retries.

The tariff's `context_window_tokens` is the operating input cap we enforce (the request body
size limit and the billing check below), not the model's real window, so that the reservation
`LLMTariff.maximum_usd()` stays a few cents.
"""

import json
from collections.abc import Callable
from decimal import ROUND_CEILING, Decimal
from typing import Any, TypeVar

import httpx
from pydantic import SecretStr

from nicheradar.integrations.contracts import ProviderError
from nicheradar.integrations.llm import LLMConfiguration, LLMTariff, TokenUsage

ENDPOINT = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

ParsedResult = TypeVar("ParsedResult")


def anthropic_actual_usd(payload: dict[str, Any], tariff: LLMTariff) -> Decimal | None:
    """Real cost from the response's usage, or None when the billing scope is unverified."""
    try:
        usage = payload["usage"]
        if usage.get("cache_creation_input_tokens", 0) != 0:
            return None  # cache writes are priced differently; we never ask for caching
        cached = usage.get("cache_read_input_tokens", 0)
        tokens = TokenUsage(
            input_tokens=usage["input_tokens"] + cached,
            output_tokens=usage["output_tokens"],
            cached_tokens=cached,
        )
        if (
            not str(payload["model"]).startswith(tariff.model)
            or tokens.input_tokens > tariff.context_window_tokens
            or tokens.output_tokens > tariff.output_tokens
        ):
            return None
        total = (
            (tokens.input_tokens - tokens.cached_tokens) * tariff.input_usd_per_million
            + tokens.cached_tokens * tariff.cached_input_usd_per_million
            + tokens.output_tokens * tariff.output_usd_per_million
        ) / 1_000_000
        return total.quantize(Decimal(".000001"), rounding=ROUND_CEILING)
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


class AnthropicClient:
    def __init__(self, secret: SecretStr, *, transport: httpx.AsyncBaseTransport | None = None):
        self.secret, self.transport = secret, transport

    async def message(
        self,
        body: dict[str, Any],
        configuration: LLMConfiguration,
        *,
        parse_fn: Callable[[dict[str, Any], LLMTariff], ParsedResult],
        max_body_bytes: int = 64_000,
        max_response_bytes: int = 64_000,
    ) -> ParsedResult:
        encoded = json.dumps(body).encode()
        if len(encoded) > max_body_bytes:
            raise ProviderError("llm_input_too_large")
        async with httpx.AsyncClient(
            transport=self.transport,
            timeout=configuration.timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            async with client.stream(
                "POST",
                ENDPOINT,
                headers={
                    "x-api-key": self.secret.get_secret_value(),
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                content=encoded,
            ) as response:
                if response.status_code != 200:
                    raise ProviderError("llm_http_error", may_have_charged=True)
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > max_response_bytes:
                        raise ProviderError("llm_response_too_large", may_have_charged=True)
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError
            return parse_fn(payload, configuration.tariff)
        except (ValueError, TypeError):
            raise ProviderError("llm_invalid_response", may_have_charged=True) from None
