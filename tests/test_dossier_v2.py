# tests/test_dossier_v2.py
"""dossier-v2: derechos y plan de automatización, con cifras que deben coincidir."""

import copy
from typing import Any
from uuid import UUID

import pytest

from nicheradar.flow_research.contracts import (
    DossierV3,
    human_minutes_per_video,
    validate_dossier,
)
from tests.flow_research_samples import valid_dossier
from tests.test_persistence import NOW

ID = UUID(int=7)


def sample() -> dict[str, Any]:
    return copy.deepcopy(valid_dossier(ID, NOW))


def problems_of(payload: dict[str, Any]) -> list[Any]:
    dossier, problems = validate_dossier(payload, NOW)
    assert dossier is None
    return problems


def paths(payload: dict[str, Any]) -> set[str]:
    return {problem["path"] for problem in problems_of(payload)}


def test_the_sample_is_a_valid_dossier_and_minutes_are_derived_from_the_flow() -> None:
    dossier, problems = validate_dossier(sample(), NOW)
    assert problems == [] and isinstance(dossier, DossierV3)
    assert human_minutes_per_video(dossier) == dossier.human_minutes_per_video == 55


def test_a_new_dossier_must_be_v3_and_the_message_says_so() -> None:
    payload = sample() | {"schema_version": "dossier-v1"}
    assert problems_of(payload) == [
        {
            "path": "schema_version",
            "message": "dossier-v1 ya no se acepta en encargos nuevos: usa dossier-v3",
        }
    ]


def test_rights_and_automation_plan_are_mandatory() -> None:
    for key in ("rights", "automation_plan"):
        payload = sample()
        del payload[key]
        assert key in paths(payload)


def test_blocked_rights_only_allow_a_no_go_recommendation() -> None:
    payload = sample()
    payload["rights"]["verdict"] = "blocked"
    assert "verdict.recommendation" in paths(payload)
    payload["verdict"]["recommendation"] = "no_go"
    dossier, problems = validate_dossier(payload, NOW)
    assert problems == [] and dossier is not None


def test_cleared_rights_cannot_hide_a_pending_permission_or_an_unknown_origin() -> None:
    payload = sample()
    payload["rights"]["materials"][0]["requires_permission"] = True
    payload["rights"]["materials"][0]["permission_plan"] = "Pedir permiso al autor de cada clip"
    assert "rights.verdict" in paths(payload)
    payload = sample()
    payload["rights"]["materials"][0]["origin"] = "unknown"
    assert "rights.verdict" in paths(payload)


def test_a_conditional_verdict_lists_its_conditions() -> None:
    payload = sample()
    payload["rights"]["verdict"] = "conditional"
    assert "rights.conditions" in paths(payload)
    payload["rights"]["conditions"] = ["Solo juegos con política explícita de monetización"]
    assert validate_dossier(payload, NOW)[1] == []


def test_a_cited_origin_needs_a_known_source_and_a_permission_needs_a_plan() -> None:
    payload = sample()
    del payload["rights"]["materials"][1]["source_id"]
    assert "rights.materials.1.source_id" in paths(payload)
    payload = sample()
    payload["rights"]["materials"][1]["source_id"] = "nope"
    assert "rights.materials.1.source_id" in paths(payload)
    payload = sample()
    payload["rights"]["materials"][0]["requires_permission"] = True
    assert "rights.materials.0.permission_plan" in paths(payload)


def test_rights_must_cover_visual_and_audio_or_voice() -> None:
    payload = sample()
    payload["rights"]["materials"] = [payload["rights"]["materials"][0]]
    assert "rights.materials" in paths(payload)


def test_every_production_step_has_a_stage_with_the_same_minutes_and_mode() -> None:
    payload = sample()
    payload["automation_plan"]["stages"].pop()
    assert "automation_plan.stages" in paths(payload)
    payload = sample()
    payload["automation_plan"]["stages"][0]["human_minutes_per_video"] = 99
    assert "automation_plan.stages.0.human_minutes_per_video" in paths(payload)
    payload = sample()
    payload["automation_plan"]["stages"][0]["mode"] = "auto"
    assert "automation_plan.stages.0.mode" in paths(payload)


def test_the_plan_must_explain_not_just_list() -> None:
    payload = sample()
    payload["automation_plan"]["stages"][0]["approach"] = "Con un modelo."
    assert any(p.endswith("approach") for p in paths(payload))
    payload = sample()
    payload["automation_plan"]["summary"] = "Corto."
    assert "automation_plan.summary" in paths(payload)


def test_stage_tools_exist_and_a_human_stage_says_why_it_stays_human() -> None:
    payload = sample()
    payload["automation_plan"]["stages"][0]["tools"][0]["name"] = "Inventada"
    assert "automation_plan.stages.0.tools.0.name" in paths(payload)
    payload = sample()
    del payload["automation_plan"]["stages"][0]["stays_human"]
    assert "automation_plan.stages.0.stays_human" in paths(payload)


def test_milestones_are_numbered_and_depend_only_on_earlier_ones() -> None:
    payload = sample()
    payload["automation_plan"]["milestones"][1]["depends_on"] = [2]
    assert "automation_plan.milestones.1.depends_on" in paths(payload)
    payload = sample()
    payload["automation_plan"]["milestones"][1]["order"] = 5
    assert "automation_plan.milestones" in paths(payload)


@pytest.mark.parametrize("where", ["rights", "automation_plan"])
def test_unknown_keys_are_rejected_without_echoing_them(where: str) -> None:
    payload = sample()
    payload[where]["sk-secret-key"] = "valor-secreto"
    problems = problems_of(payload)
    assert any(p["message"] for p in problems)
    assert "sk-secret-key" not in str(problems) and "valor-secreto" not in str(problems)
