import asyncio
import json
from datetime import timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import Engine

from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.integrations.cache import cache_key
from nicheradar.integrations.contracts import Channel, Cost, Operation
from nicheradar.integrations.llm import LLMConfiguration, OpenAISelector
from nicheradar.integrations.policies import Usage
from nicheradar.repositories.core import insert_record, seed_profile
from nicheradar.services.advertising_match import match_niche
from nicheradar.services.budget import reserve
from nicheradar.services.requests import mark_sent, prepare_request
from tests.test_persistence import NOW

CHANNEL = Channel(
    id="UC_true_crime",
    title="Casos Sin Resolver",
    description="Casos criminales reales, crimenes sin resolver y desapariciones.",
    keywords=("true crime", "cold case", "crimenes reales"),
)


def llm_configuration() -> LLMConfiguration:
    return LLMConfiguration.model_validate(
        {
            "auth_scope": "test-account",
            "tariff": {
                "version": "fixture-v1",
                "model": "fixture-model-pinned",
                "source": "invented test tariff, not actual OpenAI pricing",
                "verified_at": NOW,
                "valid_until": NOW + timedelta(days=2),
                "context_window_tokens": 10000,
                "input_usd_per_million": "1",
                "cached_input_usd_per_million": ".5",
                "output_usd_per_million": "2",
            },
            "limits": {"operation": ".05", "run": ".10", "week": ".20", "period": "1"},
        }
    )


def settings_llm_enabled() -> Settings:
    return Settings(
        mode="live",
        llm_enabled=True,
        llm_api_key=SecretStr("secret-for-mocked-http-only"),
        llm_configuration=llm_configuration(),
    )


def seed_run(connection: Any, profile_id: Any) -> dict[str, Any]:
    run_id = insert_record(
        connection,
        "analysis_runs",
        {
            "profile_id": profile_id,
            "mode": "live",
            "trigger": "channel_analysis",
            "status": "running",
            "configuration": {"channel_input": "@truecrime"},
        },
    )
    return {"id": run_id, "profile_id": profile_id, "mode": "live"}


def niche_match_payload(label: str) -> dict[str, Any]:
    return {
        "model": "fixture-model-pinned",
        "service_tier": "default",
        "status": "completed",
        "usage": {
            "input_tokens": 100,
            "input_tokens_details": {"cached_tokens": 20},
            "output_tokens": 10,
        },
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps({"niche_label": label})}],
            }
        ],
    }


def seed_niche_match_policies(connection: Any) -> None:
    for usage in (Usage.QUERY, Usage.STORAGE, Usage.DERIVED, Usage.LLM_PROCESSING):
        insert_record(
            connection,
            "provider_policies",
            {
                "provider": "openai",
                "operation": "niche_match",
                "data_type": "channel_analysis_niche_match",
                "usage": usage.value,
                "version": "fixture-v1",
                "status": "enabled",
                "evidence_source": "synthetic test policy; not permission for actual requests",
                "effective_at": NOW,
                "retention_seconds": 3600,
            },
        )


@pytest.mark.postgres
def test_match_niche_llm_disabled_returns_none(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        run = seed_run(connection, profile_id)
    result = asyncio.run(
        match_niche(
            isolated_engine, run, CreatorProfile(), Settings(llm_enabled=False), CHANNEL, NOW
        )
    )
    assert result == {"matched_niche": None, "reason": "llm_disabled"}


@pytest.mark.postgres
def test_match_niche_policy_not_enabled_returns_reason(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        run = seed_run(connection, profile_id)
    result = asyncio.run(
        match_niche(isolated_engine, run, CreatorProfile(), settings_llm_enabled(), CHANNEL, NOW)
    )
    assert result == {"matched_niche": None, "reason": "policy_not_enabled"}


@pytest.mark.postgres
def test_match_niche_budget_exhausted_degrades_cleanly(isolated_engine: Engine) -> None:
    """Regression: reserve() raising a real budget ProviderError (e.g.
    "run_budget_exhausted") used to propagate straight out of match_niche(), with
    nothing in advertising_match.py to catch it (unlike services/explanations.py's
    enrich(), which already wraps its own prepare_request/reserve/mark_sent in a
    try/except ProviderError). match_niche() must now degrade to a clean reason
    instead, matching the stage's documented "soft decline" contract."""
    profile = CreatorProfile()  # radar_usd_per_operation/run/week/month default to 0
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, profile, initial_catalog())
        run = seed_run(connection, profile_id)
        seed_niche_match_policies(connection)
    result = asyncio.run(
        match_niche(isolated_engine, run, profile, settings_llm_enabled(), CHANNEL, NOW)
    )
    assert result == {"matched_niche": None, "reason": "run_budget_exhausted"}


@pytest.mark.postgres
def test_match_niche_retry_after_lease_loss_declines_without_double_reserving(
    isolated_engine: Engine,
) -> None:
    """Regression for the retry case: if a worker crashes or loses its lease after
    prepare_request/reserve/mark_sent already committed but before the LLM call
    completes, a retry of the SAME stage calls match_niche() again with the same
    run["id"] (same idempotency key "niche_match:{run_id}"). reserve()'s own state
    check declines this as "request_already_reserved" rather than double-reserving
    -- and, with the fix above, match_niche() must surface that as a clean decline
    instead of failing the whole run."""
    profile = CreatorProfile(
        paid_limits_confirmed=True,
        radar_usd_per_operation=Decimal("0.05"),
        radar_usd_per_run=Decimal("0.10"),
        radar_usd_per_week=Decimal("0.20"),
        radar_usd_per_month=Decimal("1"),
    )
    configuration = llm_configuration()
    tariff = configuration.tariff
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, profile, initial_catalog())
        run = seed_run(connection, profile_id)
        seed_niche_match_policies(connection)
        key = cache_key(
            "openai", Operation.NICHE_MATCH, {"channel_id": CHANNEL.id}, configuration.auth_scope
        )
        request_id = prepare_request(
            connection,
            run["id"],
            "openai",
            Operation.NICHE_MATCH,
            configuration.auth_scope,
            key,
            f"niche_match:{run['id']}",
            NOW,
        )
        reserve(
            connection,
            request_id,
            profile_id,
            (Cost(unit="USD", maximum=tariff.maximum_usd(), source=tariff.source),),
            {"USD": configuration.limits},
            NOW,
            "America/Lima",
        )
        mark_sent(connection, request_id, NOW)
        # Simulate the crash: the worker never settles this request.
    result = asyncio.run(
        match_niche(isolated_engine, run, profile, settings_llm_enabled(), CHANNEL, NOW)
    )
    assert result == {"matched_niche": None, "reason": "request_already_reserved"}


@pytest.mark.postgres
def test_match_niche_llm_enabled_selects_label(isolated_engine: Engine) -> None:
    profile = CreatorProfile(
        paid_limits_confirmed=True,
        radar_usd_per_operation=Decimal("0.05"),
        radar_usd_per_run=Decimal("0.10"),
        radar_usd_per_week=Decimal("0.20"),
        radar_usd_per_month=Decimal("1"),
    )
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, profile, initial_catalog())
        run = seed_run(connection, profile_id)
        seed_niche_match_policies(connection)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "fixture-model-pinned"
        return httpx.Response(200, json=niche_match_payload("true_crime_stories"))

    selector = OpenAISelector(
        SecretStr("secret-for-mocked-http-only"), transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(
        match_niche(
            isolated_engine,
            run,
            profile,
            settings_llm_enabled(),
            CHANNEL,
            NOW,
            selector=selector,
        )
    )
    assert result["matched_niche"] == "true_crime_stories"
