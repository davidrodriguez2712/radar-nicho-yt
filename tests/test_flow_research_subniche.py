# tests/test_flow_research_subniche.py
"""Encargos de investigación de flujo ordenados desde una hipótesis de subnicho."""

import copy
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Connection

from nicheradar.flow_research.gates import Gates
from nicheradar.flow_research.service import (
    FlowResearchError,
    claim_request,
    create_request,
    submit_dossier,
)
from nicheradar.subniche_discovery.aggregate import build_profile
from nicheradar.subniche_discovery.persist import save_measurement
from nicheradar.subniche_discovery.store import approve, create_proposed, set_status
from tests.flow_research_samples import valid_dossier
from tests.subniche_samples import NOW, channel, draft, make_run, video
from tests.test_subniche_aggregate import hit

pytestmark = pytest.mark.postgres
LABEL = "subniche:history_revenge"
OPEN = Gates(0, 10_000, False, 10_000)  # sin compuertas de nicho, minutos ni calibración


def measured_hypothesis(db: Connection, *, hits: int = 3, approved: bool = True) -> None:
    run_id, _, _ = make_run(db)
    rows = [
        hit("abcdefghij"[index], traction=index == 0, low="100", high="900")
        for index in range(hits)
    ]
    hypothesis_id = create_proposed(
        db, draft(slug="history_revenge", queries=("history revenge",)), NOW
    )
    if approved:
        approve(db, "history_revenge", NOW)
    save_measurement(
        db,
        hypothesis_id=hypothesis_id,
        run_id=run_id,
        now=NOW,
        channels=[(channel("a"), [video(1)])],
        hits=rows,
        profile=build_profile(rows, rpm_source="inherited:x"),
    )


def order(db: Connection, **over: Any) -> tuple[dict[str, Any], bool]:
    args: dict[str, Any] = {"label": LABEL, "format": "long", "language": "en"}
    args.update(over)
    return create_request(
        db,
        args["label"],
        args["format"],
        args["language"],
        NOW,
        gates=OPEN,
        gate_override=args.get("gate_override"),
    )


def test_an_order_freezes_the_measurement_with_no_backlog_niche(db: Connection) -> None:
    measured_hypothesis(db)
    request, created = order(db)
    evidence = request["evidence"]
    assert created is True and request["niche_label"] == LABEL and request["status"] == "pendiente"
    assert evidence["source"] == "subniche" and evidence["niche"] is None
    assert evidence["subniche"]["slug"] == "history_revenge"
    assert evidence["measurement"]["traction_channels"] == 1
    assert evidence["language_mix"] == [{"language": "en", "share_pct": 100}]
    assert evidence["channels_available"] is True and evidence["gate"]["automation_known"] is False


def test_confidence_is_low_under_ten_channels_and_medium_from_ten(db: Connection) -> None:
    measured_hypothesis(db, hits=3)
    assert order(db)[0]["evidence"]["confidence"] == "baja"


def test_ten_channels_give_medium_confidence(db: Connection) -> None:
    measured_hypothesis(db, hits=10)
    assert order(db)[0]["evidence"]["confidence"] == "media"


@pytest.mark.parametrize("status", ["paused", "archived"])
def test_only_active_hypotheses_can_be_researched(db: Connection, status: str) -> None:
    measured_hypothesis(db)
    set_status(db, "history_revenge", status)
    with pytest.raises(FlowResearchError) as error:
        order(db)
    assert error.value.code == "subniche_not_ready"


def test_a_proposed_or_unmeasured_hypothesis_cannot_be_researched(db: Connection) -> None:
    create_proposed(db, draft(slug="history_revenge", queries=("history revenge",)), NOW)
    with pytest.raises(FlowResearchError) as proposed:
        order(db)
    approve(db, "history_revenge", NOW)
    with pytest.raises(FlowResearchError) as unmeasured:
        order(db)
    assert proposed.value.code == unmeasured.value.code == "subniche_not_ready"


def test_unknown_slug_and_prefix_without_hypothesis_are_not_found(db: Connection) -> None:
    for label in ("subniche:nope_nope", "subniche:"):
        with pytest.raises(FlowResearchError) as error:
            order(db, label=label)
        assert error.value.code == "not_found"


def test_format_and_language_must_match_the_hypothesis(db: Connection) -> None:
    measured_hypothesis(db)
    with pytest.raises(FlowResearchError) as fmt:
        order(db, format="shorts")
    with pytest.raises(FlowResearchError) as lang:
        order(db, language="es")
    assert fmt.value.code == "format_mismatch" and lang.value.code == "language_mismatch"


def test_an_active_order_is_not_duplicated(db: Connection) -> None:
    measured_hypothesis(db)
    first, _ = order(db)
    again, created = order(db)
    assert created is False and again["id"] == first["id"]


def test_a_recorded_override_is_frozen_with_the_evidence(db: Connection) -> None:
    measured_hypothesis(db)
    override = {"reason": "Experimento barato decidido por el propietario", "by": "david"}
    request, _ = order(db, gate_override=override)
    assert request["evidence"]["gate_override"]["by"] == "david"


def submit(db: Connection, request: dict[str, Any], gates: Gates, **verdict: Any) -> dict[str, Any]:
    owner = claim_request(db, request["id"], "w", NOW)["lease_owner"]
    payload = copy.deepcopy(valid_dossier(request["id"], NOW))
    payload["niche_label"] = LABEL
    payload["verdict"].update(verdict)
    return submit_dossier(db, request["id"], owner, payload, NOW, gates)


def test_a_dossier_for_a_subniche_is_accepted_when_it_passes_the_gates(db: Connection) -> None:
    measured_hypothesis(db, hits=10)
    request, _ = order(db)
    assert submit(db, request, Gates(70, 60, True, 40))["accepted"] is True


def test_minutes_and_calibration_gates_apply_to_a_subniche_dossier(db: Connection) -> None:
    measured_hypothesis(db, hits=10)
    request, _ = order(db)
    tight = Gates(70, 40, True, 10)  # la muestra: 55 minutos de régimen y 17,5 horas
    result = submit(db, request, tight)
    assert result["accepted"] is False
    message = result["problems"][0]["message"]
    assert "55" in message and "17.5" in message


def test_low_confidence_evidence_requires_declared_unknowns(db: Connection) -> None:
    measured_hypothesis(db, hits=3)
    request, _ = order(db)
    result = submit(db, request, OPEN, unknowns=[])
    assert result["accepted"] is False
    assert result["problems"][0]["path"] == "verdict.unknowns"


def test_a_dossier_for_another_label_does_not_answer_the_order(db: Connection) -> None:
    measured_hypothesis(db, hits=10)
    request, _ = order(db)
    owner = claim_request(db, request["id"], "w", NOW)["lease_owner"]
    payload = copy.deepcopy(valid_dossier(UUID(str(request["id"])), NOW))
    payload["niche_label"] = "personal_finance"
    result = submit_dossier(db, request["id"], owner, payload, NOW, OPEN)
    assert result["accepted"] is False
    assert any(p["path"] == "niche_label" for p in result["problems"])


def test_a_frozen_override_skips_the_minutes_and_calibration_gates_of_the_dossier(
    db: Connection,
) -> None:
    measured_hypothesis(db, hits=10)
    override = {"reason": "Experimento barato decidido por el propietario", "by": "david"}
    request, _ = order(db, gate_override=override)
    assert request["evidence"]["gate_override"]["by"] == "david"
    tight = Gates(70, 40, True, 10)  # la muestra: 55 minutos de régimen y 17,5 horas
    assert submit(db, request, tight)["accepted"] is True
