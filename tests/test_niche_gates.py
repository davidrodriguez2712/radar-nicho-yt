# tests/test_niche_gates.py
"""Compuertas de selección: al pedir la investigación, al entregar el dossier y al autorizar."""

import copy
from typing import Any
from uuid import UUID

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine

from nicheradar.config import Settings
from nicheradar.flow_research.gates import Gates
from nicheradar.flow_research.service import (
    FlowResearchError,
    claim_request,
    create_request,
    submit_dossier,
)
from nicheradar.market_intel.classify import TRAIT_KEYS
from nicheradar.market_intel.niches import save_decision
from tests.flow_research_samples import valid_dossier
from tests.test_flow_research_api import BASE as FLOW
from tests.test_flow_research_api import tentative_api
from tests.test_market_api import AUTH, client
from tests.test_market_intel_niches import seed_niche
from tests.test_persistence import NOW
from tests.test_pilots_api import BASE as PILOTS
from tests.test_pilots_api import authorize_body, ready_dossier

pytestmark = pytest.mark.postgres
STRICT = Gates(70, 60, True)


def niche(db: Connection, label: str, automation: int, policy: int) -> None:
    """``automation`` 0-2 applies to every automation trait: 2 → 100, 1 → 50, 0 → 0."""
    traits = {key: automation for key in TRAIT_KEYS} | {"policy_risk": policy}
    seed_niche(db, label, (1500, 2000, 2500, 3000), price=67_500, traits=traits)
    save_decision(db, label, "long", "tentativo", None, NOW)


def test_settings_defaults_are_the_documented_assumptions() -> None:
    fields = Settings.model_fields
    assert fields["gate_min_automation"].default == 90
    assert fields["gate_max_human_minutes"].default == 60
    assert fields["gate_block_high_policy_risk"].default is True
    assert Gates.from_settings(Settings(gate_min_automation=55)).min_automation == 55


def test_a_low_automation_niche_cannot_be_researched(db: Connection) -> None:
    niche(db, "gaming_general", automation=1, policy=1)
    with pytest.raises(FlowResearchError) as error:
        create_request(db, "gaming_general", "long", "en", NOW, gates=STRICT)
    assert error.value.code == "gate_failed"
    assert [reason["gate"] for reason in error.value.reasons] == ["automation"]
    assert "50" in error.value.reasons[0]["message"] and "70" in error.value.reasons[0]["message"]


def test_a_high_policy_risk_niche_cannot_be_researched_unless_the_switch_is_off(
    db: Connection,
) -> None:
    niche(db, "celebrity_news", automation=2, policy=2)
    with pytest.raises(FlowResearchError) as error:
        create_request(db, "celebrity_news", "long", "en", NOW, gates=STRICT)
    assert [reason["gate"] for reason in error.value.reasons] == ["policy_risk"]
    relaxed = Gates(70, 60, False)
    request, created = create_request(db, "celebrity_news", "long", "en", NOW, gates=relaxed)
    assert created and request["evidence"]["gate"]["policy_risk_level"] == "alto"


def test_a_passing_niche_records_the_gate_in_its_frozen_evidence(db: Connection) -> None:
    niche(db, "philosophy", automation=2, policy=1)
    request, created = create_request(db, "philosophy", "long", "en", NOW, gates=STRICT)
    gate = request["evidence"]["gate"]
    assert created and "gate_override" not in request["evidence"]
    assert gate["passed"] is True and gate["reasons"] == []
    assert (gate["min_automation"], gate["max_human_minutes"]) == (70, 60)
    assert gate["automation_value"] == 100.0 and gate["automation_known"] is True


def test_a_recorded_human_override_lets_a_failing_niche_through(db: Connection) -> None:
    niche(db, "gaming_general", automation=1, policy=1)
    override = {"reason": "Experimento barato decidido por el propietario", "by": "david"}
    request, created = create_request(
        db, "gaming_general", "long", "en", NOW, gates=STRICT, gate_override=override
    )
    assert created
    assert request["evidence"]["gate"]["passed"] is False
    assert request["evidence"]["gate_override"] == override | {"at": NOW.isoformat()}


def test_an_override_that_was_not_needed_is_not_recorded(db: Connection) -> None:
    niche(db, "philosophy", automation=2, policy=1)
    override = {"reason": "No hacía falta, pero se pasó igual", "by": "david"}
    request, _ = create_request(
        db, "philosophy", "long", "en", NOW, gates=STRICT, gate_override=override
    )
    assert "gate_override" not in request["evidence"]


def claimed(db: Connection, gates: Gates, **override: Any) -> tuple[UUID, str]:
    niche(db, "philosophy", automation=2, policy=1)
    request, _ = create_request(db, "philosophy", "long", "en", NOW, gates=gates, **override)
    owner = claim_request(db, request["id"], "w", NOW)["lease_owner"]
    return request["id"], owner


def dossier_for(request_id: UUID, **verdict: Any) -> dict[str, Any]:
    payload = copy.deepcopy(valid_dossier(request_id, NOW))
    payload["niche_label"] = "philosophy"
    payload["verdict"].update(verdict)
    return payload


def test_a_go_dossier_over_the_human_minutes_limit_is_rejected_but_no_go_is_not(
    db: Connection,
) -> None:
    request_id, owner = claimed(db, STRICT)
    tight = Gates(70, 40, True)  # the sample needs 55 minutes per video
    result = submit_dossier(db, request_id, owner, dossier_for(request_id), NOW, tight)
    assert result["accepted"] is False
    message = result["problems"][0]["message"]
    assert result["problems"][0]["path"] == "verdict.recommendation"
    assert "55" in message and "40" in message and "no_go" in message
    no_go = dossier_for(request_id, recommendation="no_go")
    assert submit_dossier(db, request_id, owner, no_go, NOW, tight)["accepted"] is True


def test_a_recorded_override_lifts_the_minutes_and_niche_gates_at_submission(
    db: Connection,
) -> None:
    niche(db, "philosophy", automation=1, policy=1)
    override = {"reason": "Experimento barato decidido por el propietario", "by": "david"}
    request, _ = create_request(
        db, "philosophy", "long", "en", NOW, gates=STRICT, gate_override=override
    )
    owner = claim_request(db, request["id"], "w", NOW)["lease_owner"]
    tight = Gates(70, 40, True)
    body = dossier_for(request["id"])
    assert submit_dossier(db, request["id"], owner, body, NOW, tight)["accepted"] is True


def test_the_niche_gate_is_checked_again_when_the_dossier_arrives(db: Connection) -> None:
    request_id, owner = claimed(db, Gates(0, 10_000, False))  # ordered while the gates were open
    result = submit_dossier(db, request_id, owner, dossier_for(request_id), NOW, Gates(101, 60))
    assert result["accepted"] is False
    assert "automatización" in result["problems"][0]["message"]


def test_blocked_rights_cannot_be_overridden_into_a_go(db: Connection) -> None:
    niche(db, "philosophy", automation=1, policy=1)
    override = {"reason": "Experimento barato decidido por el propietario", "by": "david"}
    request, _ = create_request(
        db, "philosophy", "long", "en", NOW, gates=STRICT, gate_override=override
    )
    owner = claim_request(db, request["id"], "w", NOW)["lease_owner"]
    body = dossier_for(request["id"])
    body["rights"]["verdict"] = "blocked"
    result = submit_dossier(db, request["id"], owner, body, NOW, STRICT)
    assert result["accepted"] is False
    assert any("derechos" in problem["message"] for problem in result["problems"])


def strict_api(engine: Engine) -> TestClient:
    tentative_api(engine)  # sembrado y decisión «tentativo» de personal_finance
    return client(
        engine,
        gate_min_automation=70,
        gate_max_human_minutes=60,
        gate_block_high_policy_risk=False,
    )


def test_the_api_explains_why_a_niche_was_refused_and_accepts_a_recorded_override(
    isolated_engine: Engine,
) -> None:
    with isolated_engine.begin() as connection:
        niche(connection, "motivation", automation=1, policy=1)
    api = strict_api(isolated_engine)
    body = {"niche_label": "motivation", "format": "long", "language": "en"}
    refused = api.post(FLOW, json=body, headers=AUTH)
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["code"] == "gate_failed" and detail["reasons"][0]["gate"] == "automation"
    short = {"reason": "corto", "by": "david"}
    assert api.post(FLOW, json=body | {"gate_override": short}, headers=AUTH).status_code == 422
    override = {"reason": "Experimento barato decidido por el propietario", "by": "david"}
    created = api.post(FLOW, json=body | {"gate_override": override}, headers=AUTH)
    assert created.status_code == 201
    stored = api.get(f"{FLOW}/{created.json()['id']}", headers=AUTH).json()
    assert stored["evidence"]["gate_override"]["by"] == "david"


def test_authorizing_repeats_the_gates_and_an_accepted_failure_is_recorded(
    isolated_engine: Engine,
) -> None:
    api = strict_api(isolated_engine)
    request_id = ready_dossier(api)  # el dossier de muestra pide 55 minutos: pasa con 60
    ok = api.post(PILOTS, json=authorize_body(request_id), headers=AUTH)
    assert ok.status_code == 201
    assert "COMPUERTAS" not in ok.json()["package"]["dossier"]["thesis"]

    stricter = client(
        isolated_engine,
        gate_min_automation=70,
        gate_max_human_minutes=40,
        gate_block_high_policy_risk=False,
    )
    refused = stricter.post(PILOTS, json=authorize_body(request_id), headers=AUTH)
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["code"] == "gate_failed" and detail["reasons"][0]["gate"] == "human_minutes"
    # the first pilot already holds the channel: the accepted one is left unassigned
    body = authorize_body(request_id, accept_gate_failure=True, target_channel=None)
    accepted = stricter.post(PILOTS, json=body, headers=AUTH)
    assert accepted.status_code == 201, accepted.text
    pilot = accepted.json()
    assert pilot["package"]["dossier"]["thesis"].startswith("[COMPUERTAS NO CUMPLIDAS aceptadas")
    shown = stricter.get(f"{PILOTS}/{pilot['pilot_id']}", headers=AUTH).json()
    kinds = [event["kind"] for event in shown["events"]]
    assert "gate_failure_accepted" in kinds


def test_a_stored_v1_dossier_fails_the_rights_gate_until_a_human_accepts_it(
    isolated_engine: Engine,
) -> None:
    api = strict_api(isolated_engine)
    request_id = ready_dossier(api)
    with isolated_engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE flow_research_dossiers SET schema_version = 'dossier-v1', "
                "content = (content - 'rights' - 'automation_plan') "
                '|| \'{"schema_version": "dossier-v1"}\'::jsonb WHERE request_id = :id'
            ),
            {"id": request_id},
        )
    refused = api.post(PILOTS, json=authorize_body(request_id), headers=AUTH)
    assert refused.status_code == 409
    assert refused.json()["detail"]["reasons"][0]["gate"] == "rights"
    accepted = api.post(
        PILOTS, json=authorize_body(request_id, accept_gate_failure=True), headers=AUTH
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["package"]["dossier"]["schema"] == "dossier-v1"
