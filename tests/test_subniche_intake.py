# tests/test_subniche_intake.py
import asyncio
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import Engine

from nicheradar.config import Settings
from nicheradar.integrations.anthropic import AnthropicClient
from nicheradar.subniche_discovery.intake import ManualFields, add_hypothesis
from nicheradar.subniche_discovery.store import get_hypothesis, list_hypotheses
from tests.subniche_samples import NOW, FakeReader, channel, video
from tests.test_persistence import NOW as LLM_NOW
from tests.test_subniche_propose import (
    GOOD,
    enabled_settings,
    seed_policies,
    seed_run,
    tool_payload,
)


def client_answering(data: dict[str, Any]) -> AnthropicClient:
    return AnthropicClient(
        SecretStr("secret-for-mocked-http-only"),
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=tool_payload(data))),
    )


@pytest.mark.postgres
def test_manual_add_needs_no_llm_and_creates_a_proposed_hypothesis(isolated_engine: Engine) -> None:
    result = asyncio.run(
        add_hypothesis(
            isolated_engine,
            Settings(mode="live"),
            "history revenge",
            manual=ManualFields(label="History Revenge", family="history", parent=None),
            clock=lambda: NOW,
        )
    )
    assert result["status"] == "proposed" and result["slug"] == "history_revenge"
    with isolated_engine.connect() as connection:
        assert get_hypothesis(connection, "history_revenge")["queries"] == ["history revenge"]


@pytest.mark.postgres
def test_llm_add_uses_the_proposal_and_derives_the_slug_in_code(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        seed_run(connection)
        seed_policies(connection)
    result = asyncio.run(
        add_hypothesis(
            isolated_engine,
            enabled_settings(),
            "history revenge",
            client=client_answering(GOOD),
            clock=lambda: LLM_NOW,
        )
    )
    assert result["slug"] == "history_revenge_stories"
    assert result["parent_niche"] is None or result["parent_niche"] == "historical_stories"
    assert result["queries"] == ["history revenge", "revenge that changed history"]
    assert result["llm_usd"] is not None


@pytest.mark.postgres
def test_channel_add_stores_the_channel_as_seed(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        seed_run(connection)
        seed_policies(connection)
    reader = FakeReader(
        channels={"UC" + "a" * 22: channel("a")}, uploads={"UC" + "a" * 22: (video(1),)}
    )
    result = asyncio.run(
        add_hypothesis(
            isolated_engine,
            enabled_settings(),
            "UC" + "a" * 22,
            reader=reader,
            client=client_answering({**GOOD, "parent_niche": None}),
            clock=lambda: LLM_NOW,
        )
    )
    assert result["seed_channels"] == ["UC" + "a" * 22]
    with isolated_engine.connect() as connection:
        assert len(list_hypotheses(connection)) == 1


@pytest.mark.postgres
def test_declined_llm_returns_the_reason_and_stores_nothing(isolated_engine: Engine) -> None:
    result = asyncio.run(
        add_hypothesis(isolated_engine, Settings(mode="live"), "history revenge", clock=lambda: NOW)
    )
    assert result == {"error": "llm_disabled", "hint": "use --manual to add without the LLM"}
    with isolated_engine.connect() as connection:
        assert list_hypotheses(connection) == []


@pytest.mark.postgres
def test_tweet_input_is_not_supported_yet(isolated_engine: Engine) -> None:
    result = asyncio.run(
        add_hypothesis(
            isolated_engine, enabled_settings(), "https://x.com/u/status/123", clock=lambda: NOW
        )
    )
    assert result["error"] == "tweet_not_supported_yet"


@pytest.mark.postgres
def test_duplicate_add_is_reported_not_raised(isolated_engine: Engine) -> None:
    manual = ManualFields(label="History Revenge", family="history", parent=None)
    settings = Settings(mode="live")
    asyncio.run(
        add_hypothesis(
            isolated_engine, settings, "history revenge", manual=manual, clock=lambda: NOW
        )
    )
    again = asyncio.run(
        add_hypothesis(
            isolated_engine, settings, "History  Revenge", manual=manual, clock=lambda: NOW
        )
    )
    assert again["error"].startswith("duplicate:")


@pytest.mark.postgres
def test_unknown_parent_niche_is_rejected_for_manual_adds(isolated_engine: Engine) -> None:
    manual = ManualFields(label="History Revenge", family="history", parent="not_in_catalog")
    result = asyncio.run(
        add_hypothesis(
            isolated_engine,
            Settings(mode="live"),
            "history revenge",
            manual=manual,
            clock=lambda: NOW,
        )
    )
    assert result["error"] == "unknown_parent_niche"


@pytest.mark.postgres
@pytest.mark.parametrize("label", ["!!!", "   ", "a!"])
def test_manual_label_without_usable_text_creates_nothing(
    isolated_engine: Engine, label: str
) -> None:
    result = asyncio.run(
        add_hypothesis(
            isolated_engine,
            Settings(mode="live"),
            "history revenge",
            manual=ManualFields(label=label, family="history", parent=None),
            clock=lambda: NOW,
        )
    )
    assert result == {"error": "invalid_proposal", "detail": "label has no usable text"}
    with isolated_engine.connect() as connection:
        assert list_hypotheses(connection) == []


@pytest.mark.postgres
def test_llm_label_without_usable_text_creates_nothing(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        seed_run(connection)
        seed_policies(connection)
    result = asyncio.run(
        add_hypothesis(
            isolated_engine,
            enabled_settings(),
            "history revenge",
            client=client_answering({**GOOD, "label": "!!!"}),
            clock=lambda: LLM_NOW,
        )
    )
    assert result == {"error": "invalid_proposal", "detail": "label has no usable text"}
    with isolated_engine.connect() as connection:
        assert list_hypotheses(connection) == []
