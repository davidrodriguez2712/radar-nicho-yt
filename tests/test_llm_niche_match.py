import asyncio
import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from nicheradar.integrations.contracts import ProviderError
from nicheradar.integrations.llm import (
    LLMConfiguration,
    LLMTariff,
    NicheMatchResult,
    OpenAISelector,
    niche_match_request_body,
    parse_niche_match_response,
)
from tests.test_explanations import SECRET, configuration

NICHES = (
    {"niche_label": "a", "niche_description": "desc a"},
    {"niche_label": "b", "niche_description": "desc b"},
)


def fake_tariff() -> LLMTariff:
    return configuration().tariff


def fake_configuration() -> LLMConfiguration:
    return configuration()


def niche_payload(text: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": fake_tariff().model,
        "service_tier": "default",
        "status": "completed",
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "input_tokens_details": {"cached_tokens": 0},
        },
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(text)}],
            }
        ],
    }


def test_niche_match_request_body_lists_all_options() -> None:
    body = niche_match_request_body(("kw1", "kw2"), "desc canal", NICHES, fake_tariff())
    schema_enum = body["text"]["format"]["schema"]["properties"]["niche_label"]["enum"]
    assert set(schema_enum) == {"a", "b", "ninguno"}
    assert body["store"] is False and body["tools"] == []
    assert body["background"] is False and body["service_tier"] == "default"
    assert "no confiable" in body["instructions"]
    serialized = json.dumps(body)
    assert "kw1" in serialized and "desc canal" in serialized


def test_niche_match_request_body_handles_missing_description() -> None:
    body = niche_match_request_body((), None, NICHES, fake_tariff())
    content = json.loads(body["input"][0]["content"])
    assert content["untrusted_channel_description"] is None
    assert content["untrusted_channel_keywords"] == []


def test_parse_niche_match_response_valid_label() -> None:
    result = parse_niche_match_response(
        niche_payload({"niche_label": "a"}), fake_tariff(), ("a", "b")
    )
    assert result.niche_label == "a"
    assert result.actual_usd is not None
    assert result.reason == "response_received"


def test_parse_niche_match_response_ninguno_becomes_none() -> None:
    result = parse_niche_match_response(
        niche_payload({"niche_label": "ninguno"}), fake_tariff(), ("a", "b")
    )
    assert result.niche_label is None
    assert result.reason == "response_received"


def test_parse_niche_match_response_invalid_label_rejected() -> None:
    result = parse_niche_match_response(
        niche_payload({"niche_label": "not_an_option"}), fake_tariff(), ("a", "b")
    )
    assert result.niche_label is None
    assert result.reason == "invalid_response"


def test_select_uses_custom_parse_fn() -> None:
    calls = []

    def fake_parse(payload: dict[str, Any], tariff: LLMTariff) -> NicheMatchResult:
        calls.append(payload)
        return NicheMatchResult(niche_label="a", actual_usd=None, reason="ok")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    selector = OpenAISelector(SecretStr(SECRET), transport=httpx.MockTransport(handler))
    result = asyncio.run(selector.select({"model": "m"}, fake_configuration(), parse_fn=fake_parse))
    assert calls == [{"ok": True}]
    assert isinstance(result, NicheMatchResult)
    assert result.niche_label == "a"


def test_select_still_defaults_to_claim_order_parse_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": fake_tariff().model,
                "service_tier": "default",
                "status": "completed",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "input_tokens_details": {"cached_tokens": 0},
                },
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps({"order": ["x"]})}],
                    }
                ],
            },
        )

    selector = OpenAISelector(SecretStr(SECRET), transport=httpx.MockTransport(handler))
    result = asyncio.run(selector.select({"model": "m"}, fake_configuration()))
    assert result.order == ("x",)


def test_select_oversized_body_still_rejected_with_custom_parse_fn() -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("transport should not be called for an oversized body")

    def fake_parse(payload: dict[str, Any], tariff: LLMTariff) -> NicheMatchResult:
        return NicheMatchResult(niche_label=None, actual_usd=None, reason="unused")

    selector = OpenAISelector(SecretStr(SECRET), transport=httpx.MockTransport(forbidden))
    with pytest.raises(ProviderError):
        asyncio.run(
            selector.select(
                {"model": "m", "padding": "x" * 40000},
                fake_configuration(),
                parse_fn=fake_parse,
            )
        )
