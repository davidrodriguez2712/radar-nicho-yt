from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import Engine, select

from nicheradar.api import create_app
from nicheradar.config import Settings
from nicheradar.domain.production import FitAnchor, Recipe
from nicheradar.domain.profile import CreatorProfile
from nicheradar.integrations.synthetic import SyntheticProvider
from nicheradar.repositories import schema_v1 as s
from nicheradar.services.production import ProductionPlan, evaluate_plan
from tests.test_discovery import run_pipeline
from tests.test_evaluation import fixture_scenario
from tests.test_foundation import TOKEN
from tests.test_persistence import NOW


def complete_plan() -> ProductionPlan:
    scenario = fixture_scenario()
    recipe = scenario.proposals[0].recipe
    recipe = recipe.model_copy(
        update={
            "audience_key": "english-content-viewers",
            "stages": tuple(
                stage.model_copy(
                    update={
                        "tool_key": "voice",
                        "tool_units_per_video": Decimal(1),
                        "tool_capacity_unit": "synthetic minutes",
                    }
                )
                for stage in recipe.stages
            ),
        }
    )
    return ProductionPlan(
        recipe=recipe,
        tools=scenario.tools,
        videos_per_month=4,
        radar_monthly_usd=scenario.radar_monthly_usd,
        reserve_usd=Decimal(10),
    )


def test_complete_plan_counts_fixed_cost_and_keeps_pending_reviews() -> None:
    result = evaluate_plan(complete_plan(), CreatorProfile())
    assert result["score"] == "75.00"
    assert result["resources"]["monthly_usd"] == {"low": "50", "high": "50"}
    assert result["resources"]["tool_usage"] == {"voice": "28"}
    assert result["reviews"]["rights_review"] == "pending"
    assert result["status"] == "estimated"


@pytest.mark.parametrize(
    "change",
    ["fixed_cost", "capacity", "unit", "stage_tool", "anchor", "audience", "source", "automation"],
)
def test_missing_dependency_prevents_complete_fit(change: str) -> None:
    plan = complete_plan()
    if change == "fixed_cost":
        plan = plan.model_copy(
            update={"tools": (plan.tools[0].model_copy(update={"monthly_usd": None}),)}
        )
    elif change == "capacity":
        plan = plan.model_copy(
            update={"tools": (plan.tools[0].model_copy(update={"monthly_capacity": None}),)}
        )
    elif change in {"unit", "stage_tool", "source", "automation"}:
        field, value = {
            "unit": ("tool_capacity_unit", "credits"),
            "stage_tool": ("tool_key", None),
            "source": ("source", "   "),
            "automation": ("automation", "unknown"),
        }[change]
        recipe = plan.recipe.model_copy(
            update={
                "stages": (
                    plan.recipe.stages[0].model_copy(update={field: value}),
                    *plan.recipe.stages[1:],
                )
            }
        )
        plan = plan.model_copy(update={"recipe": recipe})
    else:
        plan = plan.model_copy(
            update={
                "recipe": plan.recipe.model_copy(
                    update={"anchors": {}} if change == "anchor" else {"audience_key": None}
                )
            }
        )
    result = evaluate_plan(plan, CreatorProfile())
    assert result["score"] is None
    assert result["status"] == "incomplete"
    assert result["unknown"]


def test_volume_rework_and_limits_cannot_be_overridden_by_fit() -> None:
    plan = complete_plan().model_copy(update={"videos_per_month": 100})
    result = evaluate_plan(plan, CreatorProfile())
    assert result["score"] is not None
    assert result["resources"]["status"] == "not_viable"
    assert set(result["resources"]["exceeded"]) == {
        "monthly_usd",
        "monthly_hours",
        "voice:capacity",
    }
    plan = complete_plan()
    plan = plan.model_copy(
        update={"recipe": plan.recipe.model_copy(update={"rework_margin": Decimal(".5")})}
    )
    result = evaluate_plan(plan, CreatorProfile())
    assert result["resources"]["tool_usage"] == {"voice": "42.0"}
    assert result["resources"]["status"] == "not_viable"


def test_chat_subscription_excludes_cost_not_capacity() -> None:
    plan = complete_plan()
    tool = plan.tools[0].model_copy(
        update={
            "key": "ChatGPT",
            "excluded_existing_subscription": True,
            "monthly_usd": None,
            "monthly_capacity": None,
        }
    )
    recipe = plan.recipe.model_copy(
        update={
            "stages": tuple(
                stage.model_copy(update={"tool_key": "ChatGPT"}) for stage in plan.recipe.stages
            )
        }
    )
    result = evaluate_plan(
        plan.model_copy(update={"recipe": recipe, "tools": (tool,)}), CreatorProfile()
    )
    assert result["resources"]["monthly_usd"] == {"low": "40", "high": "40"}
    assert result["score"] is None
    assert "ChatGPT:capacity" in result["unknown"]


def test_blank_anchor_and_duplicate_tools_rejected() -> None:
    with pytest.raises(ValidationError):
        FitAnchor(grade=100, evidence="   ")
    plan = complete_plan()
    with pytest.raises(ValidationError):
        evaluate_plan(
            plan.model_copy(update={"tools": (*plan.tools, *plan.tools)}), CreatorProfile()
        )


def test_faceless_does_not_supply_automation_evidence() -> None:
    plan = complete_plan()
    with pytest.raises(ValidationError):
        Recipe.model_validate(plan.recipe.model_dump(mode="json") | {"faceless": True})
    no_anchors = plan.model_copy(update={"recipe": plan.recipe.model_copy(update={"anchors": {}})})
    assert evaluate_plan(no_anchors, CreatorProfile())["score"] is None


@pytest.mark.postgres
def test_api_immutable_assignment_and_worker_snapshot(isolated_engine: Engine) -> None:
    provider = SyntheticProvider()
    run_pipeline(isolated_engine, NOW, provider)
    client = TestClient(
        create_app(
            Settings(service_token=SecretStr(TOKEN)), engine=isolated_engine, clock=lambda: NOW
        )
    )
    with isolated_engine.connect() as connection:
        opportunity = connection.execute(
            select(s.opportunities.c.id).where(s.opportunities.c.format == "long")
        ).scalar_one()
    path = f"/api/v1/opportunities/{opportunity}/production"
    assert client.get(path).status_code == 401
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    # The default recipe auto-applies during the worker's evaluation stage, so this
    # opportunity already carries version 1 before any manual assignment.
    assert client.get(path).json()["version"] == 1
    before = client.get("/api/v1/consumption").json()
    payload: dict[str, Any] = {
        "plan": complete_plan().model_dump(mode="json"),
        "expected_version": 1,
    }
    saved = client.post(path, json=payload)
    assert saved.status_code == 201
    assert saved.json()["assessment"]["score"] == "75.00"
    assert client.get("/api/v1/consumption").json() == before
    assert client.post(path, json=payload).status_code == 409
    payload["expected_version"] = 2
    payload["plan"]["videos_per_month"] = 5
    assert client.post(path, json=payload).status_code == 409
    payload["plan"]["recipe"]["version"] = "v2"
    assert client.post(path, json=payload).status_code == 201
    assert client.get(path).json()["version"] == 3
    assert (
        client.post(
            f"/api/v1/opportunities/{opportunity}/decisions",
            json={"state": "selected", "note": "Research", "expected_version": 0},
        ).status_code
        == 200
    )
    run_pipeline(isolated_engine, NOW + timedelta(days=2), provider)
    with isolated_engine.connect() as connection:
        evaluations = (
            connection.execute(
                select(s.evaluation_versions)
                .where(s.evaluation_versions.c.opportunity_id == opportunity)
                .order_by(s.evaluation_versions.c.version)
            )
            .mappings()
            .all()
        )
        # The auto-applied default recipe fully declares tool capacity, so even the
        # first, unassigned evaluation already resolves a real Creator Fit.
        assert evaluations[0]["creator_fit"] == 88.75
        assert evaluations[-1]["creator_fit"] == 75
        assert evaluations[-1]["explanation"]["production"]["recipe_version"] == "v2"
        assert evaluations[-1]["final_score"] is None
    profile = client.get("/api/v1/profile").json()
    version = profile.pop("version_number")
    profile["weekly_hours"] = ".1"
    assert (
        client.put(
            "/api/v1/profile", json={"profile": profile, "expected_version": version}
        ).status_code
        == 200
    )
    assert client.get(path).json()["assessment"]["resources"]["status"] == "not_viable"
    with isolated_engine.connect() as connection:
        assert (
            connection.execute(
                select(s.evaluation_versions.c.explanation)
                .where(s.evaluation_versions.c.opportunity_id == opportunity)
                .order_by(s.evaluation_versions.c.version.desc())
                .limit(1)
            ).scalar_one()["production"]["resources"]["status"]
            == "viable"
        )
