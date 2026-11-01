# tests/test_dossier_v3.py
"""dossier-v3: calibración y régimen, con evidencia del régimen."""

import copy
from typing import Any
from uuid import UUID

from nicheradar.flow_research.contracts import (
    DossierV2,
    DossierV3,
    calibration_total_hours,
    validate_dossier,
)
from tests.flow_research_samples import EXIT_STATEMENT, valid_dossier, valid_dossier_v2
from tests.test_persistence import NOW

ID = UUID(int=9)


def sample() -> dict[str, Any]:
    return copy.deepcopy(valid_dossier(ID, NOW))


def paths(payload: dict[str, Any]) -> set[str]:
    dossier, problems = validate_dossier(payload, NOW)
    assert dossier is None
    return {problem["path"] for problem in problems}


def test_the_sample_is_a_valid_v3_dossier_with_derived_hours_and_regime_minutes() -> None:
    dossier, problems = validate_dossier(sample(), NOW)
    assert problems == [] and isinstance(dossier, DossierV3)
    assert dossier.human_minutes_per_video == 55  # régimen: suma del flujo
    assert dossier.calibration_hours == 17.5  # 8 + 6 × 95 / 60


def test_calibration_total_hours_adds_setup_and_per_video_minutes() -> None:
    assert calibration_total_hours(8.0, 6, 95) == 17.5
    assert calibration_total_hours(0.0, 1, 90) == 1.5


def test_v1_and_v2_are_refused_in_new_requests_with_the_v3_message() -> None:
    for version in ("dossier-v1", "dossier-v2"):
        dossier, problems = validate_dossier(sample() | {"schema_version": version}, NOW)
        assert dossier is None
        assert problems == [
            {
                "path": "schema_version",
                "message": f"{version} ya no se acepta en encargos nuevos: usa dossier-v3",
            }
        ]


def test_a_stored_v2_dossier_still_parses_as_the_legacy_model() -> None:
    legacy = DossierV2.model_validate(valid_dossier_v2(ID, NOW))
    assert legacy.human_minutes_per_video == 55


def test_calibration_and_steady_state_evidence_are_mandatory() -> None:
    for key in ("calibration", "steady_state_evidence"):
        payload = sample()
        del payload[key]
        assert key in paths(payload)


def test_a_declared_total_of_hours_is_not_allowed_and_its_value_is_not_echoed() -> None:
    payload = sample()
    payload["calibration"]["total_hours"] = 999.123456
    dossier, problems = validate_dossier(payload, NOW)
    assert dossier is None
    assert "calibration.(campo no permitido)" in {problem["path"] for problem in problems}
    assert "999.123456" not in str(problems)


def test_minutes_by_step_must_cover_every_step_once() -> None:
    payload = sample()
    del payload["calibration"]["minutes_by_step"][2]
    assert "calibration.minutes_by_step" in paths(payload)
    payload = sample()
    payload["calibration"]["minutes_by_step"][2]["step"] = "Guion"
    assert "calibration.minutes_by_step" in paths(payload)


def test_calibration_cannot_cost_fewer_minutes_than_the_regime() -> None:
    payload = sample()
    payload["calibration"]["minutes_by_step"][0]["minutes_per_video"] = 19  # régimen: 20
    assert "calibration.minutes_by_step.0.minutes_per_video" in paths(payload)


def test_a_measured_regime_declares_its_channel_minutes_and_sample() -> None:
    payload = sample()
    payload["steady_state_evidence"]["reference_minutes_per_video"] = None
    assert "steady_state_evidence.reference_minutes_per_video" in paths(payload)
    payload = sample()
    payload["steady_state_evidence"]["reference_channel"] = None
    assert "steady_state_evidence.reference_channel" in paths(payload)


def test_a_mapped_flow_equivalent_only_needs_the_reference_channel() -> None:
    payload = sample()
    evidence = payload["steady_state_evidence"]
    evidence["basis"] = "mapped_flow_equivalent"
    evidence["reference_minutes_per_video"] = None
    evidence["reference_sample_videos"] = None
    dossier, problems = validate_dossier(payload, NOW)
    assert problems == [] and dossier is not None


def estimate_payload(recommendation: str, conditions: list[str]) -> dict[str, Any]:
    payload = sample()
    payload["steady_state_evidence"] = {
        "basis": "estimate",
        "format_match": "Formato nuevo: ningún canal propio lo ha producido",
    }
    payload["verdict"]["recommendation"] = recommendation
    payload["verdict"]["conditions"] = conditions
    return payload


def test_an_estimated_regime_cannot_recommend_go() -> None:
    assert "verdict.recommendation" in paths(estimate_payload("go", []))


def test_an_estimated_regime_with_conditions_must_state_the_exit_criterion_verbatim() -> None:
    assert "verdict.conditions" in paths(estimate_payload("go_with_conditions", ["Otra cosa"]))
    ok, problems = validate_dossier(estimate_payload("go_with_conditions", [EXIT_STATEMENT]), NOW)
    assert problems == [] and ok is not None


def test_an_estimated_regime_is_fine_for_no_go() -> None:
    ok, problems = validate_dossier(estimate_payload("no_go", []), NOW)
    assert problems == [] and ok is not None


def test_a_measured_regime_can_recommend_go_without_conditions() -> None:
    payload = sample()
    payload["verdict"]["recommendation"] = "go"
    payload["verdict"]["conditions"] = []
    ok, problems = validate_dossier(payload, NOW)
    assert problems == [] and ok is not None


def test_go_with_conditions_must_list_conditions_whatever_the_basis() -> None:
    payload = sample()
    payload["verdict"]["conditions"] = []
    assert "verdict.conditions" in paths(payload)


def test_the_exit_criterion_must_fit_inside_the_calibration() -> None:
    payload = sample()
    payload["calibration"]["videos"] = 2  # el criterio pide 3 videos seguidos
    assert "calibration.exit_criterion.consecutive_videos" in paths(payload)


def test_the_exit_criterion_must_be_reachable_with_the_declared_regime() -> None:
    payload = sample()
    payload["calibration"]["exit_criterion"]["max_minutes_per_video"] = 54  # régimen: 55
    assert "calibration.exit_criterion.max_minutes_per_video" in paths(payload)
    payload["calibration"]["exit_criterion"]["max_minutes_per_video"] = 55
    ok, problems = validate_dossier(payload, NOW)
    assert problems == [] and ok is not None
