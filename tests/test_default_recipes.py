from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, select

from nicheradar.api import create_app
from nicheradar.config import Settings
from nicheradar.domain.production import rubric_score
from nicheradar.domain.profile import VideoFormat
from nicheradar.integrations.synthetic import SyntheticProvider
from nicheradar.repositories import schema_v1 as s
from nicheradar.repositories.core import get_profile
from nicheradar.services.production import (
    ProductionPlan,
    default_recipe,
    ensure_default_recipe,
    evaluate_plan,
    latest_plan,
    save_plan,
)
from tests.test_discovery import run_pipeline
from tests.test_foundation import TOKEN
from tests.test_persistence import NOW


@pytest.mark.parametrize("video_format", [VideoFormat.LONG, VideoFormat.SHORTS])
def test_default_recipe_has_a_complete_rubric_for_every_stage(video_format: VideoFormat) -> None:
    recipe = default_recipe(video_format)
    assert rubric_score(recipe) == Decimal("88.75")
    for stage in recipe.stages:
        assert stage.automation == "ai"
        assert stage.source and stage.source.strip()
        assert stage.variable_usd_per_video is not None
        assert stage.human_hours_per_video is not None


@pytest.mark.postgres
def test_worker_auto_applies_default_recipe_without_manual_input(isolated_engine: Engine) -> None:
    provider = SyntheticProvider()
    run_pipeline(isolated_engine, NOW, provider)
    with isolated_engine.connect() as connection:
        opportunity = (
            connection.execute(select(s.opportunities).where(s.opportunities.c.format == "long"))
            .mappings()
            .first()
        )
        assert opportunity is not None
        profile_id, _, profile = get_profile(connection)
        saved = latest_plan(connection, opportunity["id"], profile_id)
        assert saved is not None
        assert saved["version"] == 1
        recipe = saved["configuration"]["recipe"]
        assert recipe["audience_key"] == opportunity["audience_key"]
        assert recipe["language"] == opportunity["language"]
        assert recipe["format"] == opportunity["format"]
        # Shared-tool capacity is declared too, so the score isn't just non-fabricated
        # inputs: it actually resolves, ready to compare niches by.
        plan = ProductionPlan.model_validate(saved["configuration"])
        assessment = evaluate_plan(plan, profile)
        assert assessment["score"] == "88.75"
        assert assessment["resources"]["status"] == "viable"


@pytest.mark.postgres
def test_auto_fill_never_overwrites_a_manual_assignment(isolated_engine: Engine) -> None:
    provider = SyntheticProvider()
    run_pipeline(isolated_engine, NOW, provider)
    with isolated_engine.begin() as connection:
        opportunity = (
            connection.execute(select(s.opportunities).where(s.opportunities.c.format == "long"))
            .mappings()
            .one()
        )
        profile_id = connection.execute(select(s.creator_profiles.c.id)).scalar_one()
        # Overwrite the auto-filled version with a manual, minimal but valid recipe.
        recipe = default_recipe(VideoFormat.LONG).model_copy(
            update={
                "key": "manual-override",
                "version": "v1",
                "audience_key": opportunity["audience_key"],
                "language": opportunity["language"],
            }
        )
        manual = save_plan(
            connection,
            opportunity["id"],
            profile_id,
            ProductionPlan(recipe=recipe, videos_per_month=4),
            expected_version=1,
            now=NOW,
        )
        assert manual["version"] == 2
        assert ensure_default_recipe(connection, opportunity["id"], profile_id, NOW) is None
        current = latest_plan(connection, opportunity["id"], profile_id)
        assert current is not None
        assert current["version"] == 2


@pytest.mark.postgres
def test_default_recipe_api_seeds_versions_and_rejects_format_mismatch(
    isolated_engine: Engine,
) -> None:
    client = TestClient(
        create_app(
            Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine, clock=lambda: NOW
        )
    )
    path = "/api/v1/defaults/production-recipes/long"
    assert client.get(path).status_code == 401
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    first = client.get(path).json()
    assert first["version"] == 1
    assert first["recipe"]["format"] == "long"
    assert first["assessment"]["score"] is not None
    assert first["assessment"]["resources"]["status"] == "viable"
    edited: dict[str, Any] = first["recipe"] | {"version": "owner-v2"}
    template = {"recipe": edited, "tools": first["tools"]}
    updated = client.post(path, json={"template": template, "expected_version": 1})
    assert updated.status_code == 201
    assert updated.json()["version"] == 2
    assert client.get(path).json()["recipe"]["version"] == "owner-v2"
    mismatched = {"recipe": edited | {"format": "shorts"}, "tools": first["tools"]}
    assert (
        client.post(path, json={"template": mismatched, "expected_version": 2}).status_code == 422
    )
    assert client.post(path, json={"template": template, "expected_version": 0}).status_code == 409
