# tests/test_market_intel_priors.py
import asyncio
import json
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
from pydantic import SecretStr
from sqlalchemy import Engine

from nicheradar.domain.profile import CreatorProfile, initial_catalog
from nicheradar.integrations.llm import OpenAISelector
from nicheradar.market_intel.classify import TRAIT_KEYS
from nicheradar.market_intel.priors import (
    label_niche_priors,
    pending_priors,
    pseudo_listing,
    save_prior,
)
from nicheradar.repositories.core import seed_profile
from nicheradar.repositories.schema import niche_automation_priors
from tests.test_channel_analysis_advertising_match import settings_llm_enabled
from tests.test_market_intel_classify import (
    answer,
    forbidden_selector,
    funded_profile,
    payload,
    seed_policies,
    seed_run,
)
from tests.test_persistence import NOW

pytestmark = pytest.mark.postgres


def echo_selector(*, valid: bool = True) -> OpenAISelector:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        options = body["text"]["format"]["schema"]["properties"]["niche_label"]["enum"]
        text = answer(niche_label=options[0] if valid else "made_up_niche")
        return httpx.Response(200, json=payload(text))

    return OpenAISelector(
        SecretStr("secret-for-mocked-http-only"), transport=httpx.MockTransport(handler)
    )


def test_pseudo_listing_is_deterministic_and_describes_the_niche() -> None:
    first = pseudo_listing("personal_finance", "Finanzas personales")
    again = pseudo_listing("personal_finance", "Finanzas personales")
    assert first == again and first["id"] != pseudo_listing("credit_cards", "x")["id"]
    assert first["title"] == "personal_finance" and "Finanzas personales" in first["description"]


def test_save_prior_upserts_and_pending_skips_labelled_niches(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        first = pending_priors(connection, 500)
        assert len(first) == 218
        save_prior(connection, "personal_finance", dict.fromkeys(TRAIT_KEYS, 1), NOW)
        save_prior(connection, "personal_finance", dict.fromkeys(TRAIT_KEYS, 2), NOW)
        stored = connection.execute(sa.select(niche_automation_priors)).mappings().one()
        assert stored["traits"]["faceless"] == 2
        remaining = [item["niche_label"] for item in pending_priors(connection, 500)]
        assert len(remaining) == 217 and "personal_finance" not in remaining
        assert len(pending_priors(connection, 3)) == 3


def test_label_niche_priors_saves_each_answer_and_never_repeats(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, funded_profile(), initial_catalog())
        run = seed_run(connection, profile_id)
        seed_policies(connection)
    config = settings_llm_enabled()
    first = asyncio.run(
        label_niche_priors(isolated_engine, run, config, NOW, limit=3, selector=echo_selector())
    )
    assert first == {"pending": 3, "saved": 3, "stopped_reason": None}
    second = asyncio.run(
        label_niche_priors(isolated_engine, run, config, NOW, limit=3, selector=echo_selector())
    )
    assert second["saved"] == 3
    with isolated_engine.connect() as connection:
        labels = (
            connection.execute(sa.select(niche_automation_priors.c.niche_label)).scalars().all()
        )
    assert len(labels) == 6 and len(set(labels)) == 6


def test_invalid_answers_are_skipped_without_saving(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, funded_profile(), initial_catalog())
        run = seed_run(connection, profile_id)
        seed_policies(connection)
    result = asyncio.run(
        label_niche_priors(
            isolated_engine,
            run,
            settings_llm_enabled(),
            NOW,
            limit=2,
            selector=echo_selector(valid=False),
        )
    )
    assert result == {"pending": 2, "saved": 0, "stopped_reason": None}
    with isolated_engine.connect() as connection:
        assert (
            connection.execute(
                sa.select(sa.func.count()).select_from(niche_automation_priors)
            ).scalar_one()
            == 0
        )


def test_budget_decline_stops_the_batch_before_any_call(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        profile_id = seed_profile(connection, CreatorProfile(), initial_catalog())
        run = seed_run(connection, profile_id)
        seed_policies(connection)
    result: dict[str, Any] = asyncio.run(
        label_niche_priors(
            isolated_engine,
            run,
            settings_llm_enabled(),
            NOW,
            limit=5,
            selector=forbidden_selector(),
        )
    )
    assert result == {"pending": 5, "saved": 0, "stopped_reason": "run_budget_exhausted"}
