# tests/test_flow_research_calibration_gate.py
"""Compuerta de horas de calibración: al enviar el dossier y al autorizar el piloto."""

import copy
from uuid import UUID

import pytest
from sqlalchemy import Connection

from nicheradar.config import Settings
from nicheradar.flow_research.gates import (
    Gates,
    annotation,
    authorization_reasons,
    calibration_reasons,
)
from nicheradar.flow_research.service import claim_request, create_request, submit_dossier
from tests.flow_research_samples import valid_dossier, valid_dossier_v2
from tests.test_niche_gates import STRICT, claimed, dossier_for, niche
from tests.test_persistence import NOW

ID = UUID(int=11)
NICHE = {"automation": {"value": 95, "policy_risk": {"level": "bajo"}}, "decision": {}}


def test_calibration_hours_over_the_limit_give_one_reason_naming_both_numbers() -> None:
    reasons = calibration_reasons(50.5, Gates(max_calibration_hours=40))
    assert [reason["gate"] for reason in reasons] == ["calibration_hours"]
    assert "50.5" in reasons[0]["message"] and "40" in reasons[0]["message"]


def test_calibration_hours_at_or_under_the_limit_pass() -> None:
    assert calibration_reasons(40, Gates(max_calibration_hours=40)) == []
    assert calibration_reasons(0, Gates()) == []


def test_the_default_limit_is_forty_hours_and_comes_from_the_settings() -> None:
    assert Gates().max_calibration_hours == 40
    assert Settings.model_fields["gate_max_calibration_hours"].default == 40
    config = Settings(gate_max_calibration_hours=12.5)
    assert Gates.from_settings(config).max_calibration_hours == 12.5


def test_the_frozen_annotation_records_the_calibration_limit() -> None:
    assert annotation(NICHE, Gates(max_calibration_hours=25))["max_calibration_hours"] == 25


def test_authorization_checks_the_calibration_hours_of_a_stored_v3_dossier() -> None:
    stored = copy.deepcopy(valid_dossier(ID, NOW))  # 17,5 horas de calibración
    assert authorization_reasons(stored, NICHE, Gates(max_calibration_hours=40)) == []
    reasons = authorization_reasons(stored, NICHE, Gates(max_calibration_hours=10))
    assert [reason["gate"] for reason in reasons] == ["calibration_hours"]


def test_authorization_of_a_stored_v2_dossier_is_unchanged_and_ignores_calibration() -> None:
    stored = copy.deepcopy(valid_dossier_v2(ID, NOW))
    assert authorization_reasons(stored, NICHE, Gates(max_calibration_hours=0)) == []
    reasons = authorization_reasons(stored, NICHE, Gates(max_human_minutes=40))
    assert [reason["gate"] for reason in reasons] == ["human_minutes"]


@pytest.mark.postgres
def test_a_go_dossier_over_the_calibration_limit_is_rejected_but_no_go_is_not(
    db: Connection,
) -> None:
    request_id, owner = claimed(db, STRICT)
    tight = Gates(70, 60, True, max_calibration_hours=10)  # la muestra necesita 17,5 horas
    result = submit_dossier(db, request_id, owner, dossier_for(request_id), NOW, tight)
    assert result["accepted"] is False
    problem = result["problems"][0]
    assert problem["path"] == "verdict.recommendation"
    assert "17.5" in problem["message"] and "10" in problem["message"]
    no_go = dossier_for(request_id, recommendation="no_go")
    assert submit_dossier(db, request_id, owner, no_go, NOW, tight)["accepted"] is True


@pytest.mark.postgres
def test_a_recorded_override_lifts_the_calibration_gate(db: Connection) -> None:
    niche(db, "philosophy", automation=1, policy=1)
    override = {"reason": "Experimento barato decidido por el propietario", "by": "david"}
    request, _ = create_request(
        db, "philosophy", "long", "en", NOW, gates=STRICT, gate_override=override
    )
    owner = claim_request(db, request["id"], "w", NOW)["lease_owner"]
    tight = Gates(70, 60, True, max_calibration_hours=10)
    assert (
        submit_dossier(db, request["id"], owner, dossier_for(request["id"]), NOW, tight)["accepted"]
        is True
    )
