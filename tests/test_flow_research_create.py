# tests/test_flow_research_create.py
"""CLI y cliente para pedir una investigación pasando (o no) las compuertas."""

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine

from nicheradar.flow_research.cli import main
from nicheradar.flow_research.client import ApiError, FlowResearchClient
from tests.test_market_api import AUTH
from tests.test_niche_gates import niche, strict_api

REASON = "Experimento barato decidido por el propietario"
ARGS = ["create", "gaming_general", "--format", "long", "--language", "en"]


class Recording(FlowResearchClient):
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def create(
        self,
        niche_label: str,
        format: str,
        language: str,
        gate_override: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append((niche_label, format, language, gate_override))
        return {"id": "r1", "created": True}


def test_the_schema_command_prints_the_v2_sections(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["schema"]) == 0
    properties = json.loads(capsys.readouterr().out)["properties"]
    assert {"rights", "automation_plan"} <= set(properties)
    assert properties["schema_version"]["const"] == "dossier-v3"


def test_create_orders_research_without_an_override_by_default() -> None:
    api = Recording()
    assert main(ARGS, client=api) == 0
    assert api.calls == [("gaming_general", "long", "en", None)]


def test_create_carries_a_recorded_override_only_when_who_and_why_are_both_given() -> None:
    api = Recording()
    both = [*ARGS, "--gate-override-reason", REASON, "--gate-override-by", "david"]
    assert main(both, client=api) == 0
    assert api.calls[-1][3] == {"reason": REASON, "by": "david"}
    assert main([*ARGS, "--gate-override-reason", REASON], client=api) == 2
    assert len(api.calls) == 1


@pytest.mark.postgres
def test_the_client_surfaces_the_gate_reasons_of_a_refused_niche(isolated_engine: Engine) -> None:
    with isolated_engine.begin() as connection:
        niche(connection, "motivation", automation=1, policy=1)
    api = strict_api(isolated_engine)
    api.headers.update(AUTH)
    with pytest.raises(ApiError) as error:
        FlowResearchClient(api).create("motivation", "long", "en")
    assert error.value.status == 409
    detail: Any = error.value.detail
    assert detail["code"] == "gate_failed" and detail["reasons"][0]["gate"] == "automation"
    override = {"reason": REASON, "by": "david"}
    created = FlowResearchClient(api).create("motivation", "long", "en", override)
    assert created["created"] is True


def test_the_skill_asks_for_v3_calibration_and_the_plan_and_forbids_overrides() -> None:
    text = Path(".claude/skills/flow-research/SKILL.md").read_text()
    for needle in (
        "dossier-v3",
        "calibration",
        "steady_state_evidence",
        "régimen",
        "rights",
        "automation_plan",
        "evidence.gate",
        "max_human_minutes",
        "max_calibration_hours",
        "no_go",
        "gate_override",
        "production_flow",
        "subniche:",
        "evidence.source",
        "measurement",
    ):
        assert needle in text, needle
    assert "No pidas ni uses excepciones" in text
    assert "dossier-v1" not in text
    assert "dossier-v2" not in text
